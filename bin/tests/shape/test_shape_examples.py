from __future__ import absolute_import

from tests.shape.shape_base import *

class FirstExampleBase(TestConstraintBase):
	def makeRef(self, *slots):
		ref = None
		for slot in slots:
			ref = self.scalarIncrement(ref, slot)
		return ref

	def setUp(self):
		self.db = MockDB()
		self.sys  = analysis.shape.RegionBasedShapeAnalysis(self.db)

		x, self.xSlot, self.xExpr  = self.makeLocalObjs('x')
		y, self.ySlot, self.yExpr  = self.makeLocalObjs('y')
		z, self.zSlot, self.zExpr  = self.makeLocalObjs('z')
		t, self.tSlot, self.tExpr  = self.makeLocalObjs('t')
		q, self.qSlot, self.qExpr  = self.makeLocalObjs('q')
		self.nSlot = self.sys.canonical.fieldSlot(None, ('LowLevel', 'n'))


		self.xRef = self.makeRef(self.xSlot)
		self.yRef = self.makeRef(self.ySlot)
		self.zRef = self.makeRef(self.zSlot)
		self.tRef = self.makeRef(self.tSlot)
		self.qRef = self.makeRef(self.qSlot)
		self.nRef = self.makeRef(self.nSlot)

		self.nnRef = self.makeRef(self.nSlot, self.nSlot)
		self.ynnRef = self.makeRef(self.ySlot, self.nSlot, self.nSlot)

		self.xyRef = self.makeRef(self.xSlot, self.ySlot)
		self.xtRef = self.makeRef(self.xSlot, self.tSlot)
		self.yzRef = self.makeRef(self.ySlot, self.zSlot)

		self.xnRef = self.makeRef(self.xSlot, self.nSlot)
		self.ynRef = self.makeRef(self.ySlot, self.nSlot)
		self.tnRef = self.makeRef(self.tSlot, self.nSlot)
		self.xynRef = self.makeRef(self.xSlot, self.ySlot, self.nSlot)
		self.ytnRef = self.makeRef(self.ySlot, self.tSlot, self.nSlot)



		self.ynExpr = self.sys.canonical.fieldExpr(self.yExpr, self.nSlot)
		self.tnExpr = self.sys.canonical.fieldExpr(self.tExpr, self.nSlot)
	
		self.inputPoint  = (None, 0)
		self.outputPoint = (None, 1)

		# t = x

	def assign(self, rhs, lhs):
		self.setConstraint(analysis.shape.constraints.AssignmentConstraint(self.sys, self.inputPoint, self.outputPoint, rhs, lhs))



class TestLocalAssignConstraint(FirstExampleBase):


	def testIndex1(self):
		self.assign(self.xExpr, self.tExpr)
		# yz -> yz
		argument = (self.yzRef, None, None)
		results = [
			(self.yzRef, (self.yExpr, self.zExpr), None),
			]
		self.checkTransfer(argument, results)

	def testIndex2(self):
		self.assign(self.xExpr, self.tExpr)
		# z -> z
		argument = (self.zRef, None, None)
		results = [
			(self.zRef, (self.zExpr,), None),
			]
		self.checkTransfer(argument, results)

	def testIndex3(self):
		self.assign(self.xExpr, self.tExpr)
		# x -> xt
		argument = (self.xRef, None, None)
		results = [
			(self.xtRef, (self.xExpr, self.tExpr,), None),
			]
		self.checkTransfer(argument, results)

	def testIndex4(self):
		self.assign(self.xExpr, self.tExpr)		
		# tn -> n
		argument = (self.tnRef, None, None)
		results = [
			(self.nRef, None, None),
			]
		self.checkTransfer(argument, results)

	def testIndex5(self):
		self.assign(self.xExpr, self.tExpr)		
		# n -> n
		argument = (self.nRef, None, None)
		results = [
			(self.nRef, None, None),
			]
		self.checkTransfer(argument, results)

	def testIndex6(self):
		self.assign(self.xExpr, self.tExpr)		
		# yn -> yn
		argument = (self.ynRef, None, None)
		results = [
			(self.ynRef, (self.yExpr,), None),
			]
		self.checkTransfer(argument, results)

	def testIndex7(self):
		self.assign(self.xExpr, self.tExpr)		
		# ytn -> yn
		argument = (self.ytnRef, None, None)
		results = [
			(self.ynRef, (self.yExpr,), None),
			]
		self.checkTransfer(argument, results)

	def testTNX1(self):
		self.assign(self.tnExpr, self.xExpr)		
		# yz -> yz
		argument = (self.yzRef, None, None)
		results = [
			(self.yzRef, (self.yExpr,self.zExpr,), None),
			]
		self.checkTransfer(argument, results)

	def testTNX2(self):
		self.assign(self.tnExpr, self.xExpr)		
		# z -> z
		argument = (self.zRef, None, None)
		results = [
			(self.zRef, (self.zExpr,), None),
			]
		self.checkTransfer(argument, results)

	def testTNX3(self):
		self.assign(self.tnExpr, self.xExpr)		
		# xt -> t
		argument = (self.xtRef, None, None)
		results = [
			(self.tRef, (self.tExpr,), None),
			]
		self.checkTransfer(argument, results)

	def testTNX4(self):
		self.assign(self.tnExpr, self.xExpr)		
		# n -> n, xn
		argument = (self.nRef, None, None)
		results = [
			(self.nRef, None, (self.tnExpr,)),
			(self.xnRef, (self.tnExpr,), None),
			]
		self.checkTransfer(argument, results)

	def testTNX5(self):
		self.assign(self.tnExpr, self.xExpr)		
		# yn -> yn, xyn
		argument = (self.ynRef, None, None)
		results = [
			(self.ynRef, None, (self.tnExpr,)),
			(self.xynRef, (self.tnExpr,), None),
			]
		self.checkTransfer(argument, results)

	def testYNTN1(self):
		self.assign(self.ynExpr, self.tnExpr)		
		# yz -> yz
		argument = (self.yzRef, None, None)
		results = [
			(self.yzRef, None, None),
			]
		self.checkTransfer(argument, results)

	def testYNTN2(self):
		self.assign(self.ynExpr, self.tnExpr)		
		# z -> z
		argument = (self.xRef, None, None)
		results = [
			(self.xRef, None, None),
			]
		self.checkTransfer(argument, results)

	def testYNTN3(self):
		self.assign(self.ynExpr, self.tnExpr)		
		# t -> t
		argument = (self.tRef, None, None)
		results = [
			(self.tRef, None, None),
			]
		self.checkTransfer(argument, results)

	def testYNTN4(self):
		self.assign(self.ynExpr, self.tnExpr)		
		# n -> n, nn
		argument = (self.nRef, None, (self.tnExpr,))
		results = [
			(self.nRef, None, (self.ynExpr, self.tnExpr,)),
			(self.nnRef, (self.ynExpr, self.tnExpr,), None),
			]
		self.checkTransfer(argument, results)

	def testYNTN5(self):
		self.assign(self.ynExpr, self.tnExpr)		
		# yn -> yn, ynn
		argument = (self.ynRef, None, (self.tnExpr,))
		results = [
			(self.ynRef, None, (self.ynExpr, self.tnExpr,)),
			(self.ynnRef, (self.ynExpr, self.tnExpr,), None),
			]
		self.checkTransfer(argument, results)

	def testYNTN6(self):
		self.assign(self.ynExpr, self.tnExpr)		
		# xn -> x, xn
		argument = (self.xnRef, (self.tnExpr,),  None)
		results = [
			(self.xRef, None, None),
			(self.xnRef, (self.ynExpr, self.tnExpr,), None),
			]
		self.checkTransfer(argument, results)

	def testYNTN7(self):
		self.assign(self.ynExpr, self.tnExpr)		
		# xyn -> xy, xyn
		argument = (self.xynRef, (self.tnExpr,), None)
		results = [
			(self.xyRef, None, None),
			(self.xynRef, (self.ynExpr, self.tnExpr,), None),
			]
		self.checkTransfer(argument, results)

	def testTYN1(self):
		self.assign(self.tExpr, self.ynExpr)		
		# t -> tn
		argument = (self.tRef, None, None)
		results = [
			(self.tnRef, (self.ynExpr,), None),
			]
		self.checkTransfer(argument, results)

	def testTYN2(self):
		self.assign(self.tExpr, self.ynExpr)		
		# nn -> n
		argument = (self.nnRef, (self.tnExpr, self.ynExpr), None)
		results = [
			(self.nRef, None, (self.ynExpr,)),
			]
		self.checkTransfer(argument, results)

	def testTYN3(self):
		self.assign(self.tExpr, self.ynExpr)		
		# n -> n
		argument = (self.nRef, None, (self.tnExpr, self.ynExpr))
		results = [
			(self.nRef, None, (self.ynExpr,)),
			]
		self.checkTransfer(argument, results)

	def testTYN4(self):
		self.assign(self.tExpr, self.ynExpr)		
		# yn -> yn
		argument = (self.ynRef, None, (self.tnExpr, self.ynExpr))
		results = [
			(self.ynRef, None, (self.ynExpr,)),
			]
		self.checkTransfer(argument, results)

	def testTYN5(self):
		self.assign(self.tExpr, self.ynExpr)		
		# ynn -> yn
		argument = (self.ynnRef, (self.tnExpr, self.ynExpr), None)
		results = [
			(self.ynRef, None, (self.ynExpr,)),
			]
		self.checkTransfer(argument, results)

	def testTYN6(self):
		self.assign(self.tExpr, self.ynExpr)		
		# xn -> x
		argument = (self.xnRef, (self.tnExpr, self.ynExpr), None)
		results = [
			(self.xRef, None, None),
			]
		self.checkTransfer(argument, results)

	def testTYN7(self):
		self.assign(self.tExpr, self.ynExpr)		
		# x -> x
		argument = (self.xRef, None, None)
		results = [
			(self.xRef, None, None),
			]
		self.checkTransfer(argument, results)


	def testTYN8(self):
		self.assign(self.tExpr, self.ynExpr)		
		# xyn -> xy
		argument = (self.xynRef, (self.tnExpr, self.ynExpr), None)
		results = [
			(self.xyRef, None, None),
			]
		self.checkTransfer(argument, results)

	def testTYN9(self):
		self.assign(self.tExpr, self.ynExpr)		
		# xy -> xy
		argument = (self.xyRef, None, None)
		results = [
			(self.xyRef, None, None),
			]
		self.checkTransfer(argument, results)

	# There's more, but the tricky part seems to work?
