# Copyright 2011 Nicholas Bray
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import analysis.dataflowIR.dump
import analysis.dataflowIR.convert
from analysis.dataflowIR.transform import loadelimination
from analysis.dataflowIR.transform import dce

from  translator.dataflowtransform import correlatedanalysis

from . import treetransform, flattenoutput
from . import poolanalysis
from . import finalobjectanalysis
from . import fieldtransform, newfieldtransform, objectanalysis, newpoolanalysis, newglsltranslator
from analysis.cfgIR import dataflowsynthesis
from . import glsltranslator

from . iotransform import iotree
from . import iotransform
from . import bind
from . import shaderdescription

from util.application import compilerexceptions

from analysis.dump import dumpreport # DEBUGGING

import stats.shader

# Make a multi-level dictionary that terminates with names as its leaves.
# matcher[a][b] -> the name of path a.b
def makePathMatcher(prgm):
	root = {}
	for path, name, _input, _output in prgm.interface.glsl.attr:
		current = root

		#path = reverse(path)
		for part in path[:-1]:
			if part not in current:
				current[part] = {}
			current = current[part]

		current[path[-1]] = name

	return root


def transformOutput(context, tree, lut):
	if tree is not None and tree.impl is not None:
		node = lut[tree.impl]
		iotransform.transformOutput(context.compiler, context.dioa, context.dataflow, tree, node)

def transformInput(context, tree, lut):
	if tree is not None and tree.impl is not None:
		node = lut[tree.impl]
		iotransform.transformInput(context.compiler, context.dioa, context.dataflow, tree, node)

def transformIO(context):
	trees = context.trees
	dataflow = context.dataflow
	# NOTE the outputs are done first, as it references a local which
	# will later be transformed / eliminated by the input transform.

	### OUTPUT ###
	# Transform the output context object
	transformOutput(context, trees.contextOut, dataflow.entry.modifies)

	# Transform the return value
	transformOutput(context, trees.returnOut, dataflow.exit.reads)

	### INPUT ###
	# Transform self
	transformInput(context, trees.uniformIn, dataflow.entry.modifies)

	# Transform input context object
	transformInput(context, trees.contextIn, dataflow.entry.modifies)

	# Transform the input parameters
	for tree in trees.inputs:
		transformInput(context, tree, dataflow.entry.modifies)

def findIOTrees(context):
	dioa = context.dioa
	dataflow = context.dataflow

	trees = IOTrees()

	# Find the inputs / uniforms
	# param 0  -> uniforms
	# param 1  -> context object
	# param 2+ -> inputs

	params     = context.code.codeparameters.params
	lut        = dataflow.entry.modifies
	exist      = dataflow.entry.annotation.mask
	contextObj = iotree.getSingleObject(dioa, lut, params[1])

	trees.uniformIn = iotree.evaluateLocal(dioa, lut, exist, params[0], 'uniform')
	trees.contextIn = iotree.evaluateContextObject(dioa, lut, exist, params[1], contextObj, 'in')
	trees.inputs    = [iotree.evaluateLocal(dioa, lut, exist, p, 'in') for p in params[2:]]

	# Find the outputs
	lut   = dataflow.exit.reads
	exist = dataflow.exit.annotation.mask

	# Context object
	trees.contextOut = iotree.evaluateContextObject(dioa, lut, exist, params[1], contextObj, 'out')

	# Return values
	returns = context.code.codeparameters.returnparams
	assert len(returns) == 1, returns
	trees.returnOut = iotree.evaluateLocal(dioa, lut, exist, returns[0], 'out')

	# Find the builtin fields
	trees.match(makePathMatcher(context.prgm))

	return trees

class IOTrees(object):
	def __init__(self):
		self.uniformIn = None
		self.contextIn = None
		self.inputs  = None

		self.contextOut = None
		self.returnOut  = None

		self.inputLUT = {}
		self.outputLUT = {}

	def match(self, matcher):
		self.contextIn.match(matcher)
		self.contextOut.match(matcher)

	def buildLUTs(self):
		self.inputLUT = {}
		self.uniformIn.buildImplementationLUT(self.inputLUT)
		self.contextIn.buildImplementationLUT(self.inputLUT)
		for inp in self.inputs:
			inp.buildImplementationLUT(self.inputLUT)

		self.outputLUT = {}
		self.contextOut.buildImplementationLUT(self.outputLUT)
		self.returnOut.buildImplementationLUT(self.outputLUT)


class DataflowTransformContext(object):
	def __init__(self, compiler, prgm, code):
		self.compiler = compiler
		self.code     = code
		self.prgm     = prgm
		self.trees    = None
		self.show     = False

	def convert(self):
		self.dataflow = analysis.dataflowIR.convert.evaluateCode(self.compiler, self.code)

	def analyze(self):
		self.dioa = correlatedanalysis.evaluateDataflow(self.compiler, self.prgm, self.dataflow)
		self.dataflow = self.dioa.flat

		finalobjectanalysis.process(self.compiler, self.dataflow)

	def findAndFlattenTrees(self):
		# Transform the trees
		self.trees = findIOTrees(self)
		transformIO(self)
		iotransform.killNonintrinsicIO(self.dataflow)
		self.trees.buildLUTs()

	def reconstructCFG(self, dump=True):
		# Reconstruct the CFG from the dataflow graph
		self.cfg = dataflowsynthesis.process(self.compiler, self.dataflow, self.code.codeName(), dump=dump)

	def synthesize(self):
		self.reconstructCFG()

		# Find pools
		self.pa = poolanalysis.process(self.compiler, self.dataflow, self.dioa)

		# Translate CFG + pools into GLSL
		self.shaderCode = glsltranslator.process(self)

	def dump(self):
		self.dioa.debugDump(self.code.codeName())
		analysis.dataflowIR.dump.evaluateDataflow(self.dataflow, 'summaries\dataflow', self.code.codeName())

	def uniformTree(self):
		return self.trees.uniformIn

	def simplify(self):
		loadelimination.evaluateDataflow(self.dataflow)
		dce.evaluateDataflow(self.dataflow)

	def splitTuple(self, tree):
		indexLUT = {}
		for field, node in tree.fields.iteritems():
			if field.type == 'Array':
				index = field.name.pyobj
				indexLUT[index] = node
		return [indexLUT[i] for i in range(len(indexLUT))]

	def link(self, other):
		# Break apart the output tuple.
		outputs = self.splitTuple(self.trees.returnOut)
		inputs  = other.trees.inputs

		assert len(inputs) == len(outputs), "I/O mismatch"

		uid = 0
		for outp, inp in zip(outputs, inputs):
			uid = outp.makeLinks(inp, uid)

	def _findLiveLinked(self, node, lut, live):
		if node.link:
			for name in node.names():
				if name in lut:
					live.update(node.link.names())
					break
			else:
				node.unlink()

		for field in node.fields.itervalues():
			self._findLiveLinked(field, lut, live)

	# Find what inputs are both live and linked to another shader.
	def findLiveLinkedInputs(self):
		live = set()

		lut = self.dataflow.entry.modifies
		for inp in self.trees.inputs:
			self._findLiveLinked(inp, lut, live)

		return live

	def findLive(self, node, live):
		lut = self.dataflow.exit.reads

		for name in node.names():
			if name in lut:
				live.add(name)

		for field in node.fields.itervalues():
			self.findLive(field, live)

	def prgmDump(self):
		dumpreport.evaluate(self.compiler, self.prgm, self.code.codeName())

	def copyOriginalParams(self):
		self.originalParams = self.code.codeparameters.clone()


def evaluateShaderProgram(compiler, name, vscontext, fscontext):
	with compiler.console.scope('tree transform'):
		prgm, code, exgraph, objectInfo = treetransform.process(compiler, vscontext.code, fscontext.code)

		vscontext.prgm = prgm
		vscontext.code = code[0]
		vscontext.exgraph = exgraph
		vscontext.objectInfo = objectInfo
		vscontext.copyOriginalParams()

		fscontext.prgm = prgm
		fscontext.code = code[1]
		fscontext.exgraph = exgraph
		fscontext.objectInfo = objectInfo
		fscontext.copyOriginalParams()

	stats.shader.shaderStats(compiler, 'treetransform', name, vscontext, fscontext)

	#dumpreport.evaluate(compiler,prgm, name)

	with compiler.console.scope('flatten output'):
		vscontext.shaderdesc = flattenoutput.process(compiler, prgm, vscontext.code, False)
		fscontext.shaderdesc = flattenoutput.process(compiler, prgm, fscontext.code, True)

	#stats.shader.shaderStats(compiler, 'flattenoutput', name, vscontext, fscontext)

	with compiler.console.scope('object analysis'):
		objectanalysis.process(compiler, prgm, vscontext.code, fscontext.code)

	with compiler.console.scope('field transform'):
		newfieldtransform.process(compiler, prgm, exgraph, vscontext, fscontext)

	stats.shader.shaderStats(compiler, 'fieldtransform', name, vscontext, fscontext)


	shaderprgm = shaderdescription.ProgramDescription(prgm, name, vscontext, fscontext)
	shaderprgm.link()

	ioinfo = shaderprgm.makeIOInfo()

	with compiler.console.scope('pool analysis'):
		poolAnalysis = newpoolanalysis.process(compiler, prgm, shaderprgm, exgraph, ioinfo, vscontext, fscontext)

	return

	###########################################################

	with compiler.console.scope('translating'):
		translator = newglsltranslator.process(compiler, prgm, exgraph, poolAnalysis, shaderprgm, ioinfo)
		bind.generateBindingClass(compiler, prgm, shaderprgm, translator)

	return shaderprgm

def evaluateCode(compiler, prgm, name, vscode, fscode):
	vscontext = DataflowTransformContext(compiler, prgm, vscode)
	fscontext = DataflowTransformContext(compiler, prgm, fscode)


	shaderprgm = evaluateShaderProgram(compiler, name, vscontext, fscontext)

	return

	###########################################################

	with compiler.console.scope('debug dump'):
		dumpreport.evaluate(compiler, shaderprgm.prgm, "shaderProgram")

	raise compilerexceptions.CompilerAbort, "testing"

	with compiler.console.scope('flatten trees'):
		vscontext.findAndFlattenTrees()
		fscontext.findAndFlattenTrees()

	with compiler.console.scope('link'):
		# Ensure that identical uniforms are named the same
		vsuniforms = vscontext.uniformTree()
		fsuniforms = fscontext.uniformTree()
		vsuniforms.harmonize(fsuniforms, 'common')

		# Name the rest of the tree nodes
		# HACK avoid name conflicts by explicitly naming the trees
		vsuniforms.nameTree('uniform_vs')
		fsuniforms.nameTree('uniform_fs')

		# Link the shaders together and see what is unused.
		vscontext.link(fscontext)
		iotransform.killUnusedOutputs(fscontext)
		fscontext.simplify()

		# TODO load eliminate uniform -> varying

		# Find the live I/O
		live = fscontext.findLiveLinkedInputs()

		vscontext.findLive(vscontext.trees.contextOut, live)

		# Remove the dead outputs from the vertex shader
		def filterLive(name, slot):
			return name in live
		vscontext.dataflow.exit.filterUses(filterLive)
		vscontext.simplify()

	with compiler.console.scope('synthesize'):
		vscontext.synthesize()
		fscontext.synthesize()

		bind.generateBindingClass(vscontext, fscontext)

	with compiler.console.scope('dump'):
		vscontext.dump()
		fscontext.dump()


from language.python.shaderprogram import ShaderProgram

def translate(compiler, prgm):
	with compiler.console.scope('translate to glsl'):
		for code in prgm.interface.entryCode():
			if isinstance(code, ShaderProgram):
				name = code.name
				vs = code.vertexShaderCode()
				fs = code.fragmentShaderCode()

				evaluateCode(compiler, prgm, name, vs, fs)
