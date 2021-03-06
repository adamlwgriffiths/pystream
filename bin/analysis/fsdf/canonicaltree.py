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

import itertools
from util.monkeypatch import xcollections

class Condition(object):
	__slots__ = 'name', 'uid', 'values', 'mask'
	def __init__(self, name, uid, values):
		self.name   = name
		self.uid    = uid
		self.values = values

	def __repr__(self):
		return 'cond(%d)' % self.uid

	def __eq__(self, other):
		return self is other

	def __lt__(self, other):
		return self.uid < other.uid

	def __le__(self, other):
		return self.uid <= other.uid

	def __gt__(self, other):
		return self.uid > other.uid

	def __ge__(self, other):
		return self.uid >= other.uid

	def validate(self, values):
		for value in values:
			assert value in self.values


class ConditionManager(object):
	def __init__(self):
		self.conditions = {}

	def condition(self, name, values):
		if name not in self.conditions:
			cond = Condition(name, len(self.conditions), list(values))

			# Helper nodes
			mask = {}
			size = len(cond.values)
			for i, value in enumerate(cond.values):
				mask[value] = self.boolManager.tree(cond, tuple(self.boolManager.leaf(j==i) for j in range(size)))
			cond.mask = mask

			self.conditions[name] = cond
		else:
			cond = self.conditions[name]
			cond.validate(values)
		return cond


class AbstractNode(object):
	__slots__ = '_hash', '__weakref__'

	def __hash__(self):
		return self._hash

	def leaf(self):
		return False

	def tree(self):
		return False


class LeafNode(AbstractNode):
	cond = Condition(None, -1, 0)

	__slots__ = 'value'
	def __init__(self, value):
		self.value = value
		self._hash = hash(value)

	def __eq__(self, other):
		return self is other or (type(self) == type(other) and self.value == other.value)

	def __repr__(self):
		return 'leaf(%r)' % (self.value,)

	def iter(self, cond):
		return (self,)*len(cond.values)

	def leaf(self):
		return True

class TreeNode(AbstractNode):
	__slots__ = 'cond', 'branches'

	def __init__(self, cond, branches):
		assert len(branches) == len(cond.values), "Expected %d branches, got %d." % (len(cond.values), len(branches))
		self.cond     = cond
		self.branches = branches
		self._hash    = hash((cond, branches))

	def __eq__(self, other):
		return self is other or (type(self) == type(other) and self.cond == other.cond and self.branches == other.branches)

	def __repr__(self):
		return 'tree<%d>%r' % (self.cond.uid, self.branches)

	def iter(self, cond):
		if self.cond is cond:
			return self.branches
		else:
			return (self,)*len(cond.values)

	def branch(self, index):
		return self.branches[index]

	def tree(self):
		return True

class NoValue(object):
	__slots__ = ()
noValue = NoValue()

class UnaryTreeFunction(object):
	__slots__ = ['manager', 'func', 'cache', 'cacheHit', 'cacheMiss']

	def __init__(self, manager, func):
		self.manager    = manager
		self.func       = func
		self.cache     = {}

	def compute(self, a):
		if a.cond.uid == -1:
			# leaf computation
			result = self.manager.leaf(self.func(a.value))
		else:
			branches = tuple([self._apply(branch) for branch in a.iter(a.cond)])
			result = self.manager.tree(a.cond, branches)
		return result

	def _apply(self, a):
		# See if we've alread computed this.
		key = a
		if key in self.cache:
			self.cacheHit += 1
			return self.cache[key]
		else:
			self.cacheMiss += 1

		result = self.compute(a)

		return self.cache.setdefault(key, result)

	def __call__(self, a):
		self.cacheHit  = 0
		self.cacheMiss = 0
		result = self._apply(a)
		#print "%d/%d" % (self.cacheHit, self.cacheHit+self.cacheMiss)
		self.cache.clear() # HACK don't retain cache between computations?
		return result

class UnaryTreeVisitor(object):
	__slots__ = ['manager', 'func', 'cache', 'cacheHit', 'cacheMiss']

	def __init__(self, manager, func):
		self.manager    = manager
		self.func       = func
		self.cache      = set()

	def compute(self, context, a):
		if a.cond.uid == -1:
			# leaf computation
			self.func(context, a.value)
		else:
			for branch in a.iter(a.cond):
				self._apply(context, branch)

	def _apply(self, context, a):
		# See if we've alread computed this.
		key = a
		if key in self.cache:
			self.cacheHit += 1
		else:
			self.cacheMiss += 1

		self.compute(context, a)
		self.cache.add(key)

	def __call__(self, context, a):
		self.cacheHit  = 0
		self.cacheMiss = 0
		result = self._apply(context, a)
		#print "%d/%d" % (self.cacheHit, self.cacheHit+self.cacheMiss)
		self.cache.clear() # HACK don't retain cache between computations?
		return result

class BinaryTreeFunction(object):
	__slots__ = ['manager', 'func', 'symmetric', 'stationary',
			'leftIdentity', 'rightIdentity',
			'leftNull', 'rightNull',
			'cache', 'cacheHit', 'cacheMiss']

	def __init__(self, manager, func, symmetric=False, stationary=False,
			identity=noValue, leftIdentity=noValue, rightIdentity=noValue,
			null=noValue, leftNull=noValue, rightNull=noValue):

		assert identity is noValue or isinstance(identity, LeafNode)
		assert leftIdentity is noValue or isinstance(leftIdentity, LeafNode)
		assert rightIdentity is noValue or isinstance(rightIdentity, LeafNode)

		assert null is noValue or isinstance(null, LeafNode)
		assert leftNull is noValue or isinstance(leftNull, LeafNode)
		assert rightNull is noValue or isinstance(rightNull, LeafNode)


		self.manager    = manager
		self.func       = func
		self.symmetric  = symmetric
		self.stationary = stationary

		if symmetric or identity is not noValue:
			assert leftIdentity  is noValue
			assert rightIdentity is noValue

			self.leftIdentity  = identity
			self.rightIdentity = identity
		else:
			self.leftIdentity  = leftIdentity
			self.rightIdentity = rightIdentity

		if symmetric or null is not noValue:
			assert leftNull is noValue
			assert rightNull is noValue

			self.leftNull  = null
			self.rightNull = null
		else:
			self.leftNull  = leftNull
			self.rightNull = rightNull

		self.cache     = {}

	def compute(self, a, b):
		if self.stationary and a is b:
			# f(a, a) = a
			return a

		maxcond = max(a.cond, b.cond)

		if maxcond.uid == -1:
			# leaf/leaf computation
			result = self.manager.leaf(self.func(a.value, b.value))
		else:
			branches = tuple([self._apply(*branches) for branches in itertools.izip(a.iter(maxcond), b.iter(maxcond))])
			result = self.manager.tree(maxcond, branches)

		return result

	def _apply(self, a, b):
		# See if we've alread computed this.
		key = (a, b)
		if key in self.cache:
			self.cacheHit += 1
			return self.cache[key]
		else:
			if self.symmetric:
				# If the function is symetric, try swaping the arguments.
				altkey = (b, a)
				if altkey in self.cache:
					self.cacheHit += 1
					return self.cache[altkey]

			self.cacheMiss += 1

		# Use identities to bypass computation.
		# This is not very helpful for leaf / leaf pairs, but provides
		# an earily out for branch / leaf pairs.
		if a is self.leftIdentity:
			result = b
		elif a is self.leftNull:
			result = self.leftNull
		elif b is self.rightIdentity:
			result = a
		elif b is self.rightNull:
			result = self.rightNull
		else:
			# Cache miss, no identities, must compute
			result = self.compute(a, b)

		return self.cache.setdefault(key, result)

	def __call__(self, a, b):
		self.cacheHit  = 0
		self.cacheMiss = 0
		result = self._apply(a, b)
		#print "%d/%d" % (self.cacheHit, self.cacheHit+self.cacheMiss)
		self.cache.clear() # HACK don't retain cache between computations?
		return result

class TreeFunction(object):
	def __init__(self, manager, func, multiout=False):
		self.manager  = manager
		self.func     = func
		self.multiout = multiout
		self.cache    = {}

	def compute(self, args):
		maxcond = max(arg.cond for arg in args)

		if maxcond.uid == -1:
			# leaf/leaf computation
			unwrapped = self.func(*[arg.value for arg in args])

			if self.multiout:
				assert unwrapped is not None, (unwrapped, self.func)

				result = tuple(self.manager.leaf(res) for res in unwrapped)
			else:
				result = self.manager.leaf(unwrapped)
		else:
			branches = tuple(self._apply(branches) for branches in itertools.izip(*[arg.iter(maxcond) for arg in args]))

			if self.multiout:
				result = tuple([self.manager.tree(maxcond, branches) for branches in zip(*branches)])
			else:
				result = self.manager.tree(maxcond, branches)
		return result

	def _apply(self, args):
		# See if we've alread computed this.
		key = args
		if key in self.cache:
			self.cacheHit += 1
			return self.cache[key]
		else:
			self.cacheMiss += 1

		result = self.compute(args)

		return self.cache.setdefault(key, result)

	def __call__(self, *args):
		self.cacheHit  = 0
		self.cacheMiss = 0
		result = self._apply(args)
		#print "%d/%d" % (self.cacheHit, self.cacheHit+self.cacheMiss)
		self.cache.clear() # HACK don't retain cache between computations?
		return result


class CanonicalTreeManager(object):
	def __init__(self, coerce=None):
		if coerce is None: coerce = lambda x: x
		self.coerce = coerce

		self.trees      = xcollections.weakcache()
		self.leaves     = xcollections.weakcache()

		self.cache      = {}

	def leaf(self, value):
		return self.leaves[LeafNode(self.coerce(value))]

	def tree(self, cond, branches):
		assert isinstance(branches, tuple), type(branches)
		for branch in branches:
			assert isinstance(branch, AbstractNode), branch
			assert cond > branch.cond, (cond.uid, branch.cond.uid, branches)

		first = branches[0]
		for branch in branches:
			if branch is not first:
				break
		else:
			# They're all the same, don't make a tree.
			return first

		return self.trees[TreeNode(cond, branches)]

	def _ite(self, f, a, b):
		# If f is a constant, pick either a or b.
		if f.cond.uid == -1:
			if f.value:
				return a
			else:
				return b

		# If a and b are equal, f does not matter.
		if a is b:
			return a

		# Check the cache.
		key = (f, a, b)
		if key in self.cache:
			return self.cache[key]

		# Iterate over the branches for all nodes that have uid == maxid
		maxcond = max(f.cond, a.cond, b.cond)
		iterator = itertools.izip(f.iter(maxcond), a.iter(maxcond), b.iter(maxcond))
		computed = tuple([self._ite(*args) for args in iterator])
		result = self.tree(maxcond, computed)

		self.cache[key] = result
		return result

	def ite(self, f, a, b):
		result = self._ite(f, a, b)
		self.cache.clear()
		return result

	def _restrict(self, a, d, bound):
		if a.cond < bound:
			# Early out.
			# Should also take care of leaf cases.
			return a

		# Have we seen it before?
		if a in self.cache:
			return self.cache[a]

		index = d.get(a.cond)
		if index is not None:
			# Restrict this condition.
			result = self._restrict(a.branch(index), d, bound)
		else:
			# No restriction, keep the node.
			branches = tuple([self._restrict(branch, d, bound) for branch in a.branches])
			result = self.tree(a.cond, branches)

		self.cache[a] = result
		return result


	def restrict(self, a, d):
		# Empty restriction -> no change
		if not d: return a

		for cond, index in d.iteritems():
			assert index in cond.values, "Invalid restriction"

		bound = min(d.iterkeys())

		result = self._restrict(a, d, bound)
		self.cache.clear()
		return result


	def _simplify(self, domain, tree, default):
		# If the domain is constant, select between the tree and the default.
		if domain.leaf():
			if domain.value:
				return tree
			else:
				return default

		if tree.leaf():
			# Tree leaf, domain is not completely false.
			return tree

		key = (domain, tree)
		if key in self.cache:
			return self.cache[key]

		if domain.cond < tree.cond:
			branches = tuple([self._simplify(domain, branch, default) for branch in tree.branches])
			result   = self.tree(tree.cond, branches)
		else:
			interesting = set()
			newbranches = []
			for domainbranch, treebranch in itertools.izip(domain.branches, tree.iter(domain.cond)):
				newbranch = self._simplify(domainbranch, treebranch, default)
				newbranches.append(newbranch)

				# If the domain branch is not purely False, the data is interesting
				if not domainbranch.leaf() or domainbranch.value:
					interesting.add(newbranch)

			if len(interesting) == 1:
				result = interesting.pop()
			else:
				result = self.tree(domain.cond, tuple(newbranches))

		self.cache[key] = result
		return result

	# Simplify discards information where the domain is False.
	# Unlike ROBDD simplificaiton, tree simplification may discard only some
	# of the branches in the node.  If the remaining (simplified) branches
	# are not the same, the discarded branches are replaced with the default value.
	# ROBDD simplificaiton does not need a default values, as if there are only two branches,
	# discarding one will eliminate the node.
	# TODO in the case there domain > tree, it might be possible to get better results
	# where default comes into play?
	def simplify(self, domain, tree, default):
		result = self._simplify(domain, tree, default)
		self.cache.clear()
		return result


def BoolManager(conditions):
	manager = CanonicalTreeManager(bool)
	conditions.boolManager = manager

	manager.true  = manager.leaf(True)
	manager.false = manager.leaf(False)

	manager.and_ = BinaryTreeFunction(manager, lambda l, r: l & r,
		symmetric=True, stationary=True, identity=manager.true, null=manager.false)
	manager.or_  = BinaryTreeFunction(manager, lambda l, r: l | r,
		symmetric=True, stationary=True, identity=manager.false, null=manager.true)

	manager.maybeTrue = UnaryTreeFunction(manager, lambda s: True in s)

	# HACK use set operations, so we don't need to create a manager for individual objects?
	manager.in_       = BinaryTreeFunction(manager, lambda o, s: o.issubset(s))

	return manager

def SetManager():
	manager = CanonicalTreeManager(frozenset)

	manager.empty = manager.leaf(frozenset())

	manager.intersect = BinaryTreeFunction(manager, lambda l, r: l & r,
		symmetric=True, stationary=True, null=manager.empty)
	manager.union = BinaryTreeFunction(manager, lambda l, r: l | r,
		symmetric=True, stationary=True, identity=manager.empty)

	manager._flatten = UnaryTreeVisitor(manager, lambda context, s: context.update(s))

	def flatten(t):
		s = set()
		manager._flatten(s, t)
		return s

	manager.flatten = flatten


	return manager
