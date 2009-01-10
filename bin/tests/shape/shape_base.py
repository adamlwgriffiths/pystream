from __future__ import absolute_import

import unittest

import time

import collections

import analysis.shape

from programIR.python import ast


class MockDB(object):
	def __init__(self):
		self.invokeLUT = collections.defaultdict(set)

	def addInvocation(self, function, context, op, dstfunc, dstcontext):
		self.invokeLUT[(function, context, op)].add((dstfunc, dstcontext))


	def invocations(self, function, context, op):
		return self.invokeLUT[(function, context, op)]

class TestConstraintBase(unittest.TestCase):
	def scalarIncrement(self, rc, slot):
		next = self.sys.canonical.incrementRef(rc, slot)
		self.assertEqual(len(next), 1)
		return next[0]	

	def makeLocalObjs(self, name):
		lcl = ast.Local(name)
		slot = self.sys.canonical.localSlot(lcl)
		expr = self.sys.canonical.localExpr(slot)
		return lcl, slot, expr


	def convert(self, row, entry):
		type_  = None
		region = None
		current, hits, misses = row
		if isinstance(hits, tuple): hits = set(hits)
		if isinstance(misses, tuple): misses = set(misses)
		external = False
		
		return self.sys.canonical.configuration(type_, region, entry, current), self.sys.canonical.secondary(hits, misses, external)

	def countOutputs(self):
		count = 0
		for point, context, index in self.sys.environment._secondary.iterkeys():
			if point == self.outputPoint:
				count += 1
		return count

	def setInOut(self, inp, outp):
		self.inputPoint = inp
		self.outputPoint = outp

	def setConstraint(self, constraint):
		self.constraint = constraint
		self.setInOut(constraint.inputPoint, constraint.outputPoint)

	def checkTransfer(self, argument, results):
		inputPoint = self.inputPoint
		outputPoint = self.outputPoint
		context = None

		entry = argument[0]
		conf, secondary = self.convert(argument, entry)


		self.sys.environment.merge(self.sys, inputPoint, context, conf, secondary)
		self.sys.process()

		self.assertEqual(self.countOutputs(), len(results))

		for row in results:
			econf, esecondary = self.convert(row, entry)
			secondary = self.sys.environment.secondary(outputPoint, context, econf)

			self.assertNotEqual(secondary, None, "Expected output %r not found." % econf)
			self.assertEqual(secondary.hits, esecondary.hits)
			self.assertEqual(secondary.misses, esecondary.misses)	


class TestCompoundConstraintBase(TestConstraintBase):
	def makeConstraints(self, func):
		builder = self.sys.constraintbuilder
		builder.process(func)
		return builder.statementPre[func], builder.statementPost[func]


	def createInput(self, ref):
		entry = ref if self.cs else None
		argument = (ref, None, None)
		conf, secondary = self.convert(argument, entry)
		self.setInput(conf, secondary)

	def setInput(self, conf, secondary):
		self.sys.environment.merge(self.sys, self.inputPoint, self.context, conf, secondary)

	def dumpPoint(self, givenPoint):
		mapping = self.sys.environment._secondary
		       
		for (point, context, conf), secondary in mapping.iteritems():
			if point != givenPoint: continue

			print conf.object, conf.region
			print conf.entrySet
			print conf.currentSet
			if secondary.hits:
				print "hits"
				for hit in secondary.hits:
					print '\t', hit
			if secondary.misses:
				print "misses"
				for miss in secondary.misses:
					print '\t', miss
			print "externalReferences: %r" % secondary.externalReferences
			print

	def dumpStatistics(self):
		print "Entries:", len(self.sys.environment._secondary)
		print "Unique Config:", len(self.sys.canonical.configurationCache)
		print "Max Worklist:", self.sys.worklist.maxLength
		print "Steps:", "%d/%d" % (self.sys.worklist.usefulSteps, self.sys.worklist.steps)


	def process(self):
		start = time.clock()
		self.sys.process()
		end = time.clock()
		self.elapsed = end-start

		self.dump(self.outputPoint)

	def dump(self, point):
		print
		print "/%s\\" % ("*"*80)
		self.dumpPoint(point)
		self.dumpStatistics()
		if self.elapsed < 1.0:
			print "Time: %.1f ms" % (self.elapsed*1000.0)
		elif self.elapsed < 10.0:
			print "Time: %.2f s" % (self.elapsed)
		else:
			print "Time: %.1f s" % (self.elapsed)
		print "\\%s/" % ("*"*80)
		print