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
import time

from analysis.cpa import base
from analysis.storegraph import storegraph
import language.python.ast as ast
import language.python.annotations as annotations

from PADS.StrongConnectivity import StronglyConnectedComponents

from . database import structure
from . database import tupleset
from . database import mapping
from . database import lattice

from analysis.astcollector import getOps

contextSchema   = structure.WildcardSchema()
operationSchema = structure.TypeSchema((ast.Expression, ast.Statement))
codeSchema      = structure.CallbackSchema(lambda code: code.isCode())

def wrapOpContext(schema):
	schema = mapping.MappingSchema(contextSchema, schema)
	schema = mapping.MappingSchema(operationSchema, schema)
	schema = mapping.MappingSchema(codeSchema, schema)
	return schema

def wrapCodeContext(schema):
	schema = mapping.MappingSchema(contextSchema, schema)
	schema = mapping.MappingSchema(codeSchema, schema)
	return schema



opDataflowSchema = wrapOpContext(lattice.setUnionSchema)

invokesStruct = structure.StructureSchema(
	('code',    codeSchema),
	('context', contextSchema)
	)
invokesSchema = wrapOpContext(tupleset.TupleSetSchema(invokesStruct))

invokeSourcesStruct = structure.StructureSchema(
	('code',      codeSchema),
	('operation', operationSchema),
	('context',   contextSchema)
	)
invokeSourcesSchema = wrapCodeContext(tupleset.TupleSetSchema(invokeSourcesStruct))


def invertInvokes(invokes):
	invokeSources = invokeSourcesSchema.instance()

	for code, ops in invokes:
		assert code.isCode(), type(code)
		for op, contexts in ops:
			for context, invs in contexts:
				for dstCode, dstContext in invs:
					invokeSources[dstCode][dstContext].add(code, op, context)
	return invokeSources

def filteredSCC(G):
	o = []
	for g in StronglyConnectedComponents(G):
		if len(g) > 1:
			o.append(g)
	return o


class ObjectInfo(object):
	def __init__(self, obj):
		self.obj            = obj
		self.refersTo       = set()
		self.referedFrom    = set()
		self.localReference = set()
		self.heldByClosure  = set()

		# Reasonable defaults
		self.globallyVisible   = obj.xtype.isExisting()
		self.externallyVisible = obj.xtype.isExternal()

	def isReachableFrom(self, refs):
		return bool(self.heldByClosure.intersection(refs))

	def leaks(self):
		return self.globallyVisible or self.externallyVisible

	def updateHeldBy(self, newHeld):
		assert not self.leaks(), self.obj

		diff = newHeld-self.heldByClosure
		if diff:
			self.heldByClosure.update(diff)
			return True
		else:
			return False

class ReadModifyAnalysis(object):
	def __init__(self, liveCode, invokeSources):
		self.invokeSources       = invokeSources

		self.contextReads    = collections.defaultdict(set)
		self.contextModifies = collections.defaultdict(set)

		self.collectDB(liveCode)

	def handleModifies(self, code, op, modifies):
		if modifies[0]:
			for cindex, context in enumerate(code.annotation.contexts):
				slots = modifies[1][cindex]
				if op is not None: self.opModifyDB[code][op].merge(context, slots)
				self.contextModifies[(code, context)].update(slots)
				self.allModifies.update(slots)

	def handleReads(self, code, op, reads):
		if reads[0]:
			for cindex, context in enumerate(code.annotation.contexts):
				slots    = reads[1][cindex]
				filtered = set([slot for slot in slots if slot in self.allModifies])
				if op is not None: self.opReadDB[code][op].merge(context, filtered)
				self.contextReads[(code, context)].update(filtered)
				self.allReads.update(slots)


	def handleAllocates(self, code, op, allocates):
		if allocates[0]:
			for cindex, context in enumerate(code.annotation.contexts):
				self.allocations[(code, context)].update(allocates[1][cindex])


	def collectDB(self, liveCode):
		self.allReads        = set()
		self.allModifies     = set()

		self.opReadDB   = opDataflowSchema.instance()
		self.opModifyDB = opDataflowSchema.instance()

		self.allocations = collections.defaultdict(set)

		# Copy modifies
		for code in liveCode:
			self.handleModifies(code, None, code.annotation.codeModifies)
			ops, lcls = getOps(code)
			for op in ops:
				self.handleModifies(code, op, op.annotation.opModifies)

		# Copy reads
		for code in liveCode:
			self.handleReads(code, None, code.annotation.codeReads)
			self.handleAllocates(code, None, code.annotation.codeAllocates)

			ops, lcls = getOps(code)
			for op in ops:
				self.handleReads(code, op, op.annotation.opReads)
				self.handleAllocates(code, op, op.annotation.opAllocates)

	def process(self, killed):
		self.killed = killed
		self.processReads()
		self.processModifies()


	def processReads(self):
		self.dirty = set()

		for (code, context), values in self.contextReads.iteritems():
			if values: self.dirty.add((code, context))


		while self.dirty:
			current = self.dirty.pop()
			self.processContextReads(current)

	def processContextReads(self, current):
		currentF, currentC = current

		for prev in self.invokeSources[currentF][currentC]:
			prevF, prevO, prevC = prev

			prevRead = self.opReadDB[prevF][prevO]

			killed = self.killed[(prevF, prevO, prevC)][(currentF, currentC)]

			# Propigate reads
			filtered = set([value for value in self.contextReads[(currentF, currentC)] if value.object not in killed])
			current = prevRead[prevC]
			diff = filtered-current if current else filtered

			if diff:
				self.contextReads[(prevF, prevC)].update(diff)
				prevRead.merge(prevC, diff)
				self.dirty.add((prevF, prevC))



	def processModifies(self):
		self.dirty = set()

		for (code, context), values in self.contextModifies.iteritems():
			if values: self.dirty.add((code, context))

		while self.dirty:
			current = self.dirty.pop()
			self.processContextModifies(current)

	def processContextModifies(self, current):
		currentF, currentC = current

		for prev in self.invokeSources[currentF][currentC]:
			prevF, prevO, prevC = prev

			prevMod = self.opModifyDB[prevF][prevO]

			killed = self.killed[(prevF, prevO, prevC)][(currentF, currentC)]

			# Propigate modifies
			filtered = set([value for value in self.contextModifies[(currentF, currentC)] if value.object not in killed])
			#diff = filtered-self.opModifies[prev]
			current = prevMod[prevC]
			diff = filtered-current if current else filtered
			if diff:
				self.contextModifies[(prevF, prevC)].update(diff)
				prevMod.merge(prevC, diff)
				self.dirty.add((prevF, prevC))

class DFSSearcher(object):
	def __init__(self):
		self._stack   = []
		self._touched = set()

	def enqueue(self, *children):
		for child in children:
			if child not in self._touched:
				self._touched.add(child)
				self._stack.append(child)

	def process(self):
		while self._stack:
			current = self._stack.pop()
			self.visit(current)

class ObjectSearcher(DFSSearcher):
	def __init__(self, la):
		DFSSearcher.__init__(self)
		self.la = la

	def visit(self, obj):
		objInfo = self.la.getObjectInfo(obj)
		for slot in obj:
			for next in slot:
				nextInfo = self.la.getObjectInfo(next)
				objInfo.refersTo.add(nextInfo)
				nextInfo.referedFrom.add(objInfo)
				self.enqueue(next)

class LifetimeAnalysis(object):
	def __init__(self):
		self.heapReferedToByHeap = collections.defaultdict(set)
		self.heapReferedToByCode = collections.defaultdict(set)

		self.codeRefersToHeap = collections.defaultdict(set)

		self.objects = {}

		self.globallyVisible = set()
		self.externallyVisible = set()

	def getObjectInfo(self, obj):
		assert isinstance(obj, storegraph.ObjectNode), type(obj)
		if obj not in self.objects:
			info = ObjectInfo(obj)
			self.objects[obj] = info
		else:
			info = self.objects[obj]
		return info


	def findGloballyVisible(self):
		# Globally visible
		active = set()
		for info in self.objects.itervalues():
			if info.globallyVisible:
				active.add(info)
				self.globallyVisible.add(info.obj)

		while active:
			current = active.pop()
			for ref in current.refersTo:
				if not ref.globallyVisible:
					ref.globallyVisible = True
					active.add(ref)
					self.globallyVisible.add(ref.obj)


	def findExternallyVisible(self):
		# Externally visible
		active = set()
		for info in self.objects.itervalues():
			if info.externallyVisible:
				active.add(info)
				self.externallyVisible.add(info.obj)

		while active:
			current = active.pop()
			for ref in current.refersTo:
				if not ref.externallyVisible:
					ref.externallyVisible = True
					active.add(ref)
					self.externallyVisible.add(ref.obj)

	def propagateVisibility(self):
		self.findGloballyVisible()
		self.findExternallyVisible()
		self.escapes = self.globallyVisible.union(self.externallyVisible)

		# Annotate the objects
		for info in self.objects.itervalues():
			info.obj.leaks = info.leaks()

	def objEscapes(self, obj):
		assert not isinstance(obj, ObjectInfo), obj
		return obj in self.escapes

	def propagateHeld(self):
		dirty = set()

		for obj, info in self.objects.iteritems():
			if not self.objEscapes(obj):
				if info.updateHeldBy(info.referedFrom):
					for dst in info.refersTo:
						if not self.objEscapes(dst.obj): dirty.add(dst)

		while dirty:
			current = dirty.pop()
			assert not self.objEscapes(current.obj), current.obj

			# Find the new heldby
			newHeld = set()
			for prev in current.referedFrom:
				newHeld.update(prev.heldByClosure)

			if current.updateHeldBy(newHeld):
				# Mark as dirty
				for dst in current.refersTo:
					if not self.objEscapes(dst.obj): dirty.add(dst)

		#self.displayHistogram()


	def displayHistogram(self):
		# Display a histogram of the number of live heap objects
		# that may hold (directly or indirectly) a given live heap object.
		hist = collections.defaultdict(lambda:0)
		for obj, info in self.objects.iteritems():
			if not obj in self.escapes:
				if len(info.heldByClosure) >= 4:
					print obj
					for other in info.heldByClosure:
						print '\t', other.obj
					print
				hist[len(info.heldByClosure)] += 1
			else:
				hist[-1] += 1

		keys = sorted(hist.iterkeys())
		for key in keys:
			print key, hist[key]

	def inferScope(self):
		# Figure out how far back on the stack the object may propagate
		self.live = collections.defaultdict(set)
		self.killed = collections.defaultdict(lambda: collections.defaultdict(set))

		# Seed the inital dirty set
		self.dirty = set()
		for (code, context), objs in self.rm.allocations.iteritems():
			noescape = objs-self.escapes
			self.live[(code, context)].update(noescape)
			self.dirty.update(self.invokeSources[code][context])

		while self.dirty:
			current = self.dirty.pop()
			self.processScope(current)

		self.convertKills()


	def convertKills(self):
		# Convert kills on edges to kills on nodes.
		self.contextKilled = collections.defaultdict(set)
		for dstF, contexts in self.invokeSources:
			for dstC, srcs in contexts:
				if not srcs: continue

				killedAll = None
				for srcF, srcO, srcC in srcs:
					newKilled = self.killed[(srcF, srcO, srcC)][(dstF, dstC)]
					if killedAll is None:
						killedAll = newKilled
					else:
						killedAll = killedAll.intersection(newKilled)

				if killedAll:
					self.contextKilled[(dstF, dstC)].update(killedAll)

		for code, context in self.entries:
			self.contextKilled[(code, context)].update(self.live[(code, context)])

	def processScope(self, current):
		currentF, currentO, currentC = current
		assert currentF.isCode(), type(currentF)

		operationSchema.validate(currentO)

		newLive = set()

		live = self.live

		for dstF, dstC in self.invokes[currentF][currentO][currentC]:
			for dstLive in live[(dstF, dstC)]:
				if dstLive in live[(currentF, currentC)]:
					continue
				if dstLive in newLive:
					continue

				refs     = self.codeRefersToHeap[(currentF, currentC)]
				refinfos = [self.getObjectInfo(ref) for ref in refs]

				# Could the object stay live?
				if dstLive in refs:
					# Directly held
					newLive.add(dstLive)
				elif self.getObjectInfo(dstLive).isReachableFrom(refinfos):
					# Indirectly held
					newLive.add(dstLive)
				else:
					# The object will never propagate along this invocation
					self.killed[(currentF, currentO, currentC)][(dstF, dstC)].add(dstLive)

		if newLive:
			# Propigate dirty
			live[(currentF, currentC)].update(newLive)
			self.dirty.update(self.invokeSources[currentF][currentC])


	def gatherInvokes(self, liveCode, entryContexts):
		invokesDB = invokesSchema.instance()

		self.entries = set()

		for code in liveCode:
			for context in code.annotation.contexts:
				if context in entryContexts:
					self.entries.add((code, context))


			assert code.isCode(), type(code)
			ops, lcls = getOps(code)
			for op in ops:
				invokes = op.annotation.invokes
				if invokes is not None:
					for cindex, context in enumerate(code.annotation.contexts):
						opInvokes = invokes[1][cindex]

						for dstF, dstC in opInvokes:
							assert dstF.isCode(), type(dstF)
							invokesDB[code][op][context].add(dstF, dstC)


			for lcl in lcls:
				refs = lcl.annotation.references
				if refs is None:
					continue

				for cindex, context in enumerate(code.annotation.contexts):
					for ref in refs[1][cindex]:
						obj = self.getObjectInfo(ref)
						obj.localReference.add(code)

						self.codeRefersToHeap[(code, context)].add(ref)

		self.invokes       = invokesDB
		self.invokeSources = invertInvokes(invokesDB)

	def markVisible(self, lcl, cindex):
		if lcl is not None:
			refs = lcl.annotation.references[1][cindex]
			for ref in refs:
				obj = self.getObjectInfo(ref)
				obj.externallyVisible = True


	def gatherSlots(self, liveCode, entryContexts):

		searcher = ObjectSearcher(self)

		for code in liveCode:
			callee = code.codeParameters()

			ops, lcls = getOps(code)
			for lcl in lcls:
				for ref in lcl.annotation.references[0]:
					searcher.enqueue(ref)

			# Mark the return parameters for external contexts as visible.
			for cindex, context in enumerate(code.annotation.contexts):
				if context in entryContexts:
					for param in callee.returnparams:
						self.markVisible(param, cindex)

		searcher.process()


	def process(self, compiler, prgm):
		with compiler.console.scope('solve'):
			entryContexts = prgm.interface.entryContexts()

			self.gatherSlots(prgm.liveCode, entryContexts)
			self.gatherInvokes(prgm.liveCode, entryContexts)

			self.propagateVisibility()
			self.propagateHeld()

			self.rm = ReadModifyAnalysis(prgm.liveCode, self.invokeSources)
			self.inferScope()
			self.rm.process(self.killed)

		with compiler.console.scope('annotate'):
			self.createDB(compiler, prgm)

		del self.rm

	def createDB(self, compiler, prgm):
		self.annotationCount = 0
		self.annotationCache = {}

		readDB   = self.rm.opReadDB
		modifyDB = self.rm.opModifyDB
		self.allocations = self.rm.allocations

		for code in prgm.liveCode:
			# Annotate the code
			live   = []
			killed = []
			for cindex, context in enumerate(code.annotation.contexts):
				key = (code, context)
				live.append(annotations.annotationSet(self.live[key]))
				killed.append(annotations.annotationSet(self.contextKilled[key]))

			code.rewriteAnnotation(live=annotations.makeContextualAnnotation(live),
				killed=annotations.makeContextualAnnotation(killed))

			# Annotate the ops
			ops, lcls = getOps(code)
			for op in ops:
				# TODO is this a good HACK?
				# if not op.annotation.invokes[0]: continue

				reads    = readDB[code][op]
				modifies = modifyDB[code][op]

				rout = []
				mout = []
				aout = []

				for cindex, context in enumerate(code.annotation.contexts):
					# HACK if an operation directly reads a field, but it is never modified
					# it still must appear in the reads annotation so cloning behaves correctly!
					reads.merge(context, op.annotation.opReads[1][cindex])

					creads = reads[context]
					creads = annotations.annotationSet(creads) if creads else ()
					rout.append(creads)

					cmod = modifies[context]
					cmod = annotations.annotationSet(cmod) if cmod else ()
					mout.append(cmod)


					kills = self.killed[(code, op, context)]

					calloc = set()
					for dstCode, dstContext in op.annotation.invokes[1][cindex]:
						live = self.live[(dstCode, dstContext)]
						killed = kills[(dstCode, dstContext)]
						calloc.update(live-killed)

					calloc.update(op.annotation.opAllocates[1][cindex])

					aout.append(annotations.annotationSet(calloc))

				opReads     = annotations.makeContextualAnnotation(rout)
				opModifies  = annotations.makeContextualAnnotation(mout)
				opAllocates = annotations.makeContextualAnnotation(aout)

				opReads     = self.annotationCache.setdefault(opReads,     opReads)
				opModifies  = self.annotationCache.setdefault(opModifies,  opModifies)
				opAllocates = self.annotationCache.setdefault(opAllocates, opAllocates)
				self.annotationCount += 3

				op.rewriteAnnotation(reads=opReads, modifies=opModifies, allocates=opAllocates)

		compiler.console.output("Annotation compression %f - %d" % (float(len(self.annotationCache))/max(self.annotationCount, 1), self.annotationCount))

		del self.annotationCache
		del self.annotationCount

def evaluate(compiler, prgm):
	with compiler.console.scope('lifetime analysis'):
		la = LifetimeAnalysis().process(compiler, prgm)
