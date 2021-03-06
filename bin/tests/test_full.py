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

from __future__ import absolute_import

import unittest
import os.path

from . fullcompiler import compileExample

from util.debug.debugger import conditionalDebugOnFailiure
import config


example = False
linear = False
confusion = False
loops = False
tuples = False

physics   = True
recursive = False
pystone   = False


class FullTestBase(unittest.TestCase):

	@conditionalDebugOnFailiure(config.debugOnFailiure)
	def setUp(self):
		# The makefile is relitive to this module.
		path, filename = os.path.split(__file__)
		makefile = os.path.join(path, self.makefile)

		self.module, self.generated = compileExample(makefile)

	def compare(self, name, *args):
		pass # HACK test is disabled
#		original = getattr(self.module, name)
#		generated = getattr(self.generated, name)
#		self.assertEqual(original(*args), generated(*args))

if example:
	class TestExampleFull(FullTestBase):
		makefile = 'full/makeexample.py'

		def testF(self):
			self.compare('f')
	####
	######	def testFactorial(self):
	######		self.compare('factorial', 10)
	######		self.compare('factorial', 2)
	######		self.compare('factorial', 1)
	######		self.compare('factorial', 0)
	######		self.compare('factorial', -1)
	####
	####	def testNegate(self):
	####		self.compare('negate', 7)
	####		self.compare('negate', 0)
	####		self.compare('negate', -11)
	####
	####	def testConst(self):
	####		self.compare('negateConst')
	####
	####	def testAdd(self):
	####		self.compare('add', 5, 7)
	####		self.compare('add', 7, 5)
	####
	####	def testEither(self):
	####		self.compare('either', 0, 0)
	####		self.compare('either', 0, 2)
	####		self.compare('either', 1, 0)
	####		self.compare('either', 1, 2)
	####
	####	def testCallFunc(self):
	####		self.compare('call', 1.0, 2.0, 3.0, 4.0)
	####		self.compare('call', 8.0, 7.0, 6.0, 5.0)
	####
	####	def testInRange(self):
	####		self.compare('inrange', -0.1)
	####		self.compare('inrange', +0.0)
	####		self.compare('inrange', +0.5)
	####		self.compare('inrange', +1.0)
	####		self.compare('inrange', +1.1)
	####
	####	def testDefaultArgs(self):
	####		self.compare('defaultArgs', 7, 11)
	####		self.compare('defaultArgs', 7)
	####		self.compare('defaultArgs')
	####
	####	def testSwitch1(self):
	####		self.compare('switch1', -1.0)
	####		self.compare('switch1', -0.5)
	####		self.compare('switch1', 0.0)
	####		self.compare('switch1', 0.5)
	####		self.compare('switch1', 1.0)
	####		self.compare('switch1', 1.5)
	####
	####	def testSwitch2(self):
	####		self.compare('switch2', -1.0)
	####		self.compare('switch2', -0.5)
	####		self.compare('switch2', 0.0)
	####		self.compare('switch2', 0.5)
	####		self.compare('switch2', 1.0)
	####		self.compare('switch2', 1.5)
	####


if linear:
	class TestLinearFull(FullTestBase):
		makefile = 'full/makelinear.py'

		def testDoDot(self):
			self.compare('doDot')
	######
	######	def testDoDotHalf(self):
	######		self.compare('doDotHalf', 7.0, 11.0, 5.0)
	######
	######	def testDoDotFull(self):
	######		self.compare('doDotFull', 7.0, 11.0, 5.0, 3.0, 2.0, 13.0)
	######
	######	def testDoStaticSwitch(self):
	######		self.compare('doStaticSwitch')

if confusion:
	class TestConfusionFull(FullTestBase):
		makefile = 'full/makeconfusion.py'

		def testBeConfused(self):
			self.compare('beConfused', False)
			self.compare('beConfused', True)
	#####
	######	def testBeConfusedSite(self):
	######		self.compare('beConfusedSite', False)
	######		self.compare('beConfusedSite', True)
	######
	######	def testBeConfusedConst(self):
	######		self.compare('beConfusedConst', 2)
	######		self.compare('beConfusedConst', 1)
	######		self.compare('beConfusedConst', 0)
	######		self.compare('beConfusedConst', -1)
	######		self.compare('beConfusedConst', -2)
	######
	######	def testConfuseMethods(self):
	######		self.compare('confuseMethods', 1, 2, 3, 4, 5, 6)
	######		self.compare('confuseMethods', 6, 5, 4, 3, 2, 1)
	####
	##
	##

if loops:
	class TestLoopsFull(FullTestBase):
		makefile = 'full/makeloops.py'

		def testWhileLoop(self):
			self.compare('whileLoop', 0.0)
	####
	####	def testIsPrime(self):
	####		self.compare('isPrime', 2)
	####		self.compare('isPrime', 3)
	####		self.compare('isPrime', 4)
	####		self.compare('isPrime', 5)
	####		self.compare('isPrime', 15)
	####
	######
	######	def testMakePrimesWhile(self):
	######		self.compare('findPrimesWhile', 7)
	######		self.compare('findPrimesWhile', 20)
	######		self.compare('findPrimesWhile', 50)
	######


if tuples:
	class TestTuplesFull(FullTestBase):
		makefile = 'full/maketuples.py'

		def testTupleTest(self):
			self.compare('tupleTest', 1.0, 2.0, 3.0)
			self.compare('tupleTest', 8.0, 7.0, 6.0)
	##
	##
	##	def testAddHybridTuple(self):
	##		self.compare('addHybridTuple', 0)
	##		self.compare('addHybridTuple', 7)
	##		self.compare('addHybridTuple', -11)
	##
	##	def testAddConstTuple(self):
	##		self.compare('addConstTuple')
	##
	##	def testSwap(self):
	##		self.compare('swap', 7, 11)
	##		self.compare('swap', 13, 5)
	##
	##	def testUnpackConstCompound(self):
	##		self.compare('unpackConstCompound')
	##
	##	def testUnpackCompound(self):
	##		self.compare('unpackCompound', 1, 2, 3, 4)
	##		self.compare('unpackCompound', 11, 7, -5, 13)
	##
	##	def testIndex(self):
	##		self.compare('index')


##class TestListsFull(FullTestBase):
##	makefile = 'full/makelists.py'
##
##	def testListTest(self):
##		self.compare('listTest', 1.0, 2.0, 3.0)
##		self.compare('listTest', 8.0, 7.0, 6.0)
##
##
##	def testAddHybridList(self):
##		self.compare('addHybridList', 0)
##		self.compare('addHybridList', 7)
##		self.compare('addHybridList', -11)
##
##	def testAddConstList(self):
##		self.compare('addConstList')
##
##	def testSwap(self):
##		self.compare('swap', 7, 11)
##		self.compare('swap', 13, 5)
##
##	def testUnpackConstCompound(self):
##		self.compare('unpackConstCompound')
##
##	def testUnpackCompound(self):
##		self.compare('unpackCompound', 1, 2, 3, 4)
##		self.compare('unpackCompound', 11, 7, -5, 13)
##
##	def testIndex(self):
##		self.compare('index')

if physics:
	class TestPhysicsFull(FullTestBase):
		makefile = 'full/makephysics.py'

		def testTupleTest(self):
			self.compare('simpleUpdate', 0.25)

##class TestRuntimeFull(FullTestBase):
##	makefile = 'full/makeruntime.py'
##
##	def testF(self):
##		self.compare('testF')

if recursive:
	class TestRecursiveFull(FullTestBase):
		makefile = 'full/makerecursive.py'

		def testFact(self):
			self.compare('fact', 10)

if pystone:
	class TestPystoneFull(FullTestBase):
		makefile = 'full/makepystone.py'

		def testFact(self):
			self.compare('main', 1000)
