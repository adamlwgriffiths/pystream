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

import collections
import itertools
from util.io import formatting

from . import base, simpleimagebuilder

from analysis.storegraph import storegraph, canonicalobjects, extendedtypes
import analysis.cpasignature

from . constraintextractor import ExtractDataflow

from . constraints import AssignmentConstraint, DirectCallConstraint

from . import codecloner

# Only used for creating return variables
from language.python import ast
from language.python import program
from language.python import annotations

from optimization.callconverter import callConverter

from util.python.apply import applyFunction

from analysis.astcollector import getOps

# For keeping track of how much time we spend decompiling.
import time

import util.canonical

# For allocation
import types

#########################
### Utility functions ###
#########################

def foldFunctionIR(extractor, func, vargs=(), kargs={}):
	newvargs = [arg.pyobj for arg in vargs]

	assert not kargs, kargs
	newkargs = {}

	result = applyFunction(func, newvargs, newkargs)
	return extractor.getObject(result)


###############################
### Main class for analysis ###
###############################

class InterproceduralDataflow(object):
	def __init__(self, compiler, graph, opPathLength, clone):
		self.decompileTime = 0
		self.console   = compiler.console
		self.extractor = compiler.extractor
		self.clone = clone # Should we copy the code before annotating it?

		# Has the context been constructed?
		self.liveContexts = set()

		self.liveCode = set()

		# Constraint information, for debugging
		self.constraints = []

		# The worklist
		self.dirty = collections.deque()

		self.canonical = graph.canonical
		self._canonicalContext = util.canonical.CanonicalCache(base.AnalysisContext)

		# Controls how many previous ops are remembered by a context.
		# TODO remember prior CPA signatures?
		self.opPathLength = opPathLength
		self.cache = {}

		# Information for contextual operations.
		self.opAllocates      = collections.defaultdict(set)
		self.opReads          = collections.defaultdict(set)
		self.opModifies       = collections.defaultdict(set)
		self.opInvokes        = collections.defaultdict(set)

		self.codeContexts     = collections.defaultdict(set)

		self.storeGraph = graph

		# Setup the "external" context, used for creaing bogus slots.
		self.externalOp  = util.canonical.Sentinel('<externalOp>')

		self.externalFunction = ast.Code('external', ast.CodeParameters(None, [], [], [], None, None, [ast.Local('internal_return')]), ast.Suite([]))
		externalSignature = self._signature(self.externalFunction, None, ())
		opPath  = self.initialOpPath()
		self.externalFunctionContext = self._canonicalContext(externalSignature, opPath, self.storeGraph)
		self.codeContexts[self.externalFunction].add(self.externalFunctionContext)


		# For vargs
		self.tupleClass = self.extractor.getObject(tuple)
		self.ensureLoaded(self.tupleClass)

		# For kargs
		self.dictionaryClass = self.extractor.getObject(dict)
		self.ensureLoaded(self.dictionaryClass)

		self.entryPointOp = {}

	def initialOpPath(self):
		if self.opPathLength == 0:
			path = None
		elif self.opPathLength == 1:
			path = self.externalOp
		else:
			path = (self.externalOp,)*self.opPathLength

		return self.cache.setdefault(path, path)

	def advanceOpPath(self, original, op):
		assert not isinstance(op, canonicalobjects.OpContext)

		if self.opPathLength == 0:
			path = None
		elif self.opPathLength == 1:
			path = op
		else:
			path = original[1:]+(op,)

		return self.cache.setdefault(path, path)
	def ensureLoaded(self, obj):
		# TODO the timing is no longer guaranteed, as the store graph bypasses this...
		start = time.clock()
		self.extractor.ensureLoaded(obj)
		self.decompileTime += time.clock()-start

	def getCall(self, obj):
		start = time.clock()
		result = self.extractor.getCall(obj)
		self.decompileTime += time.clock()-start
		return result

	def logAllocation(self, cop, cobj):
		assert isinstance(cobj, storegraph.ObjectNode), type(cobj)
		self.opAllocates[(cop.code, cop.op, cop.context)].add(cobj)


	def logRead(self, cop, slot):
		assert isinstance(slot, storegraph.SlotNode), type(slot)
		self.opReads[(cop.code, cop.op, cop.context)].add(slot)


	def logModify(self, cop, slot):
		assert isinstance(slot, storegraph.SlotNode), type(slot)
		self.opModifies[(cop.code, cop.op, cop.context)].add(slot)


	def constraint(self, constraint):
		self.constraints.append(constraint)

	def _signature(self, code, selfparam, params):
		def checkParam(param):
			return param is None or param is analysis.cpasignature.Any or isinstance(param, extendedtypes.ExtendedType)

		assert code.isCode(), type(code)
		assert checkParam(selfparam), selfparam
		for param in params:
			assert checkParam(param), param

		return analysis.cpasignature.CPASignature(code, selfparam, params)

	def canonicalContext(self, srcOp, code, selfparam, params):
		assert isinstance(srcOp, canonicalobjects.OpContext), type(srcOp)
		assert code.isCode(), type(code)

		sig     = self._signature(code, selfparam, params)
		opPath  = self.advanceOpPath(srcOp.context.opPath, srcOp.op)

		if code.annotation.primitive:
			# Call path does not matter.
			opPath = None

		context = self._canonicalContext(sig, opPath, self.storeGraph)

		# Mark that we created the context.
		self.codeContexts[code].add(context)

		return context

	# This is the policy that determines what names a given allocation gets.
	def extendedInstanceType(self, context, xtype, op):
		self.ensureLoaded(xtype.obj)
		instObj = xtype.obj.abstractInstance()

		pyobj = xtype.obj.pyobj
		if pyobj is types.MethodType:
			# Method types are named by their function and instance
			sig = context.signature
			# TODO check that this is "new"?
			if len(sig.params) == 4:
				# sig.params[0] is the type object for __new__
				func = sig.params[1]
				inst = sig.params[2]
				return self.canonical.methodType(func, inst, instObj, op)
		elif pyobj is types.TupleType or pyobj is types.ListType or pyobj is types.DictionaryType:
			# Containers are named by the signature of the context they're allocated in.
			return self.canonical.contextType(context, instObj, op)

		return self.canonical.pathType(context.opPath, instObj, op)

	def process(self):
		while self.dirty:
			current = self.dirty.popleft()
			current.process()

	def createAssign(self, source, dest):
		AssignmentConstraint(self, source, dest)

	def fold(self, targetcontext):
		def notConst(obj):
			return obj is analysis.cpasignature.Any or (obj is not None and not obj.obj.isConstant())

		sig = targetcontext.signature
		code = sig.code

		if code.annotation.dynamicFold:
			# It's foldable.
			p = code.codeparameters
			assert p.vparam is None, code.name
			assert p.kparam is None, code.name

			# TODO folding with constant vargs?
			# HACK the internal selfparam is usually not "constant" as it's a function, so we ignore it?
			#if notConst(sig.selfparam): return False
			for param in sig.params:
				if notConst(param): return False

			params = [param.obj for param in sig.params]
			result = foldFunctionIR(self.extractor, code.annotation.dynamicFold, params)
			resultxtype = self.canonical.existingType(result)

			# Set the return value
			assert len(p.returnparams) == 1
			name = self.canonical.localName(code, p.returnparams[0], targetcontext)
			returnSource = self.storeGraph.root(name)
			returnSource.initializeType(resultxtype)

			return True

		return False

	def initializeContext(self, context):
		# Don't bother if the call can never happen.
		if context.invocationMaySucceed(self):
			# Caller-independant initalization.
			if context not in self.liveContexts:
				# Mark as initialized
				self.liveContexts.add(context)

				code = context.signature.code

				# HACK convert the calls before analysis to eliminate UnpackTuple nodes.
				callConverter(self.extractor, code)

				if code not in self.liveCode:
					self.liveCode.add(code)

				# Check to see if we can just fold it.
				# Dynamic folding only calculates the output,
				# so we still evaluate the constraints.
				folded = self.fold(context)

				# Extract the constraints
				exdf = ExtractDataflow(self, context, folded)
				exdf.process()
			return True
		return False

	def bindCall(self, cop, caller, targetcontext):
		assert isinstance(cop, canonicalobjects.OpContext), type(cop)

		sig = targetcontext.signature
		code = sig.code

		dst = self.canonical.codeContext(code, targetcontext)
		if dst not in self.opInvokes[cop]:
			# Record the invocation
			self.opInvokes[cop].add(dst)

			if self.initializeContext(targetcontext):
				targetcontext.bindParameters(self, caller)

	def makeExternalSlot(self, name):
		code    = self.externalFunction
		context = self.externalFunctionContext
		dummyLocal = ast.Local(name)
		dummyName = self.canonical.localName(code, dummyLocal, context)
		dummySlot = self.storeGraph.root(dummyName)
		return dummySlot

	def createEntryOp(self, entryPoint):
		code    = self.externalFunction
		context = self.externalFunctionContext

		# Make sure each op is unique.
		op = util.canonical.Sentinel('entry point op')
		cop = self.canonical.opContext(code, op, context)
		self.entryPointOp[entryPoint] = cop
		return cop

	def getArgSlot(self, xtypes):
		if not xtypes: return None
		slot = self.makeExternalSlot('arg')
		slot.initializeTypes(xtypes)
		return slot

	def addEntryPoint(self, entryPoint, args):
		# The call point
		cop = self.createEntryOp(entryPoint)

		selfSlot = self.getArgSlot(args.selfarg)
		argSlots = [self.getArgSlot(arg) for arg in args.args]
		kwds = []
		varg = self.getArgSlot(args.vargs)
		karg = self.getArgSlot(args.kargs)
		returnSlots = [self.makeExternalSlot('return_%s' % entryPoint.name())]

		# Create the initial constraint
		DirectCallConstraint(self, cop, entryPoint.code, selfSlot, argSlots, kwds, varg, karg, returnSlots)


	def solve(self):
		start = time.clock()
		# Process
		self.process()

		end = time.clock()

		self.solveTime = end-start-self.decompileTime


	### Annotation methods ###

	def collectContexts(self, lut, contexts):
		cdata  = [annotations.annotationSet(lut[context]) for context in contexts]
		data = annotations.makeContextualAnnotation(cdata)

		data = self.annotationCache.setdefault(data, data)
		self.annotationCount += 1

		return data

	def collectRMA(self, code, contexts, op):
		creads     = [annotations.annotationSet(self.opReads[(code, op, context)]) for context in contexts]
		reads     = annotations.makeContextualAnnotation(creads)

		cmodifies  = [annotations.annotationSet(self.opModifies[(code, op, context)]) for context in contexts]
		modifies  = annotations.makeContextualAnnotation(cmodifies)

		callocates = [annotations.annotationSet(self.opAllocates[(code, op, context)]) for context in contexts]
		allocates = annotations.makeContextualAnnotation(callocates)

		reads     = self.annotationCache.setdefault(reads, reads)
		modifies  = self.annotationCache.setdefault(modifies, modifies)
		allocates = self.annotationCache.setdefault(allocates, allocates)
		self.annotationCount += 3

		return reads, modifies, allocates

	def annotateCode(self, code, contexts, cloner):
		newcode = cloner.code(code)

		contexts = tuple(contexts)
		newcode.rewriteAnnotation(contexts=contexts)

		# Creating vparam and kparam objects produces side effects...
		# Store them in the code annotation
		reads, modifies, allocates = self.collectRMA(code, contexts, None)
		newcode.rewriteAnnotation(codeReads=reads, codeModifies=modifies, codeAllocates=allocates)

		return contexts

	def mergeAbstractCode(self, code, cloner):
		newcode = cloner.code(code)

		# This is done after the ops and locals are annotated as the "abstractReads", etc. may depends on the annotations.
		reads     = annotations.mergeContextualAnnotation(newcode.annotation.codeReads, newcode.abstractReads())
		modifies  = annotations.mergeContextualAnnotation(newcode.annotation.codeModifies, newcode.abstractModifies())
		allocates = annotations.mergeContextualAnnotation(newcode.annotation.codeAllocates, newcode.abstractAllocates())

		reads     = self.annotationCache.setdefault(reads, reads)
		modifies  = self.annotationCache.setdefault(modifies, modifies)
		allocates = self.annotationCache.setdefault(allocates, allocates)
		self.annotationCount += 3

		newcode.rewriteAnnotation(codeReads=reads, codeModifies=modifies, codeAllocates=allocates)

	def annotateEntryPoints(self, cloner):
		# TODO redirect code?

		# Find the contexts that a given entryPoint invokes
		for entryPoint, op in self.entryPointOp.iteritems():
			entryPoint.code = cloner.code(entryPoint.code)
			contexts = [ccontext.context for ccontext in self.opInvokes[op]]
			entryPoint.contexts = contexts

	def reindexAnnotations(self, cloner):
		# Re-index the invocations
		invokeLUT = collections.defaultdict(lambda: collections.defaultdict(set))
		for srcop, dsts in self.opInvokes.iteritems():
			for dst in dsts:
				newdstcode = cloner.code(dst.code)
				invokeLUT[(srcop.code, srcop.op)][srcop.context].add((newdstcode, dst.context))
		self.invokeLUT = invokeLUT

		# Re-index the locals
		lclLUT = collections.defaultdict(lambda: collections.defaultdict(set))
		for slot in self.storeGraph:
			name = slot.slotName
			if name.isLocal():
				lclLUT[(name.code, name.local)][name.context] = slot
			elif name.isExisting():
				lclLUT[(name.code, name.object)][name.context] = slot
		self.lclLUT = lclLUT

	def annotateOps(self, code, contexts, ops, cloner):
		for op in ops:
			invokes = self.collectContexts(self.invokeLUT[(code, op)], contexts)
			reads, modifies, allocates = self.collectRMA(code, contexts, op)

			newop = cloner.op(op)

			newop.rewriteAnnotation(
				invokes=invokes,
				opReads=reads,
				opModifies=modifies,
				opAllocates=allocates,
				)

	def annotateLocals(self, code, contexts, lcls, cloner):
		for lcl in lcls:
			if isinstance(lcl, ast.Existing):
				contextLclLUT = self.lclLUT[(code, lcl.object)]
				newlcl = cloner.op(lcl) # HACK?
			else:
				contextLclLUT = self.lclLUT[(code, lcl)]
				newlcl = cloner.lcl(lcl)
			references = self.collectContexts(contextLclLUT, contexts)

			newlcl.rewriteAnnotation(references=references)

	def annotate(self):
		if self.clone:
			cloner = codecloner.FunctionCloner(self.codeContexts.iterkeys())

			# Translate the live code
			self.liveCode = set([cloner.code(code) for code in self.liveCode])
		else:
			cloner = codecloner.NullCloner(self.codeContexts.iterkeys())

		self.annotationCount = 0
		self.annotationCache = {}

		self.reindexAnnotations(cloner)

		self.annotateEntryPoints(cloner)

		for code, contexts in self.codeContexts.iteritems():
			if code is self.externalFunction: continue

			cloner.process(code)

			contexts = self.annotateCode(code, contexts, cloner)

			ops, lcls = getOps(code)

			self.annotateOps(code, contexts, ops, cloner)
			self.annotateLocals(code, contexts, lcls, cloner)

			self.mergeAbstractCode(code, cloner)

		self.console.output("Annotation compression %f - %d" % (float(len(self.annotationCache))/max(self.annotationCount, 1), self.annotationCount))

		del self.annotationCache
		del self.annotationCount

	### Debugging methods ###

	def checkConstraints(self):
		badConstraints = []
		allBad = set()
		allWrite = set()
		for c in self.constraints:
			bad = c.getBad()
			if bad:
				badConstraints.append((c, bad))
				allBad.update(bad)
				allWrite.update(c.writes())

		# Try to find the constraints that started the problem.
		for c, bad in badConstraints:
			if not allWrite.issuperset(bad):
				c.check(self.console)

	def slotMemory(self):
		return self.storeGraph.setManager.memory()

	def dumpSolveInfo(self):
		console = self.console
		console.output("Constraints:   %d" % len(self.constraints))
		console.output("Contexts:      %d" % len(self.liveContexts))
		console.output("Code:          %d" % len(self.liveCode))
		console.output("Contexts/Code: %.1f" % (float(len(self.liveContexts))/max(len(self.liveCode), 1)))
		console.output("Slot Memory:   %s" % formatting.memorySize(self.slotMemory()))
		console.output('')
		console.output("Decompile:     %s" % formatting.elapsedTime(self.decompileTime))
		console.output("Solve:         %s" % formatting.elapsedTime(self.solveTime))
		console.output('')


def evaluateWithImage(compiler, prgm, opPathLength=0, firstPass=True, clone=False):
	with compiler.console.scope('cpa analysis'):
		dataflow = InterproceduralDataflow(compiler, prgm.storeGraph, opPathLength, clone)
		dataflow.firstPass = firstPass # HACK for debugging

		for entryPoint, args in prgm.entryPoints:
			dataflow.addEntryPoint(entryPoint, args)

		try:
			with compiler.console.scope('solve'):
				dataflow.solve()
				dataflow.checkConstraints()
				dataflow.dumpSolveInfo()
		finally:
			# Helps free up memory.
			with compiler.console.scope('cleanup'):
				del dataflow.constraints
				dataflow.storeGraph.removeObservers()

			with compiler.console.scope('annotate'):
				dataflow.annotate()

			prgm.liveCode   = dataflow.liveCode

		return dataflow

def evaluate(compiler, prgm, opPathLength=0, firstPass=True):
	simpleimagebuilder.build(compiler, prgm)
	return evaluateWithImage(compiler, prgm, opPathLength, firstPass)
