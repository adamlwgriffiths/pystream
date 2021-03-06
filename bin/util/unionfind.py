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

class UnionFind(object):
	__slots__ = 'parents', 'weights'

	def __init__(self):
		self.parents = {}
		self.weights = {}

	def __getitem__(self, obj):
		if obj not in self.parents:
			return obj
		else:
			return self.getItemCompress(obj)

	def __iter__(self):
		return self.parents.iterkeys()

	def getItemCompress(self, obj):
		parent = self.parents[obj]
		if parent == obj:
			return parent
		else:
			root = self.getItemCompress(parent)
			self.parents[obj] = root
			return root

	def union(self, first, *objs):
		if objs:
			biggestRoot = self[first]
			maxWeight   = self.weights.get(biggestRoot, 1)
			roots       = set()
			roots.add(biggestRoot)

			for obj in objs:
				root   = self[obj]
				if root not in roots:
					weight = self.weights.get(root, 1)
					if weight > maxWeight:
						biggestRoot = root
						maxWeight   = weight
					roots.add(root)

			# The biggest root is intentionall left in roots,
			# So we ensure that self.parents[biggestRoot] exists.
			if len(roots) > 1:
				weight = 0
				for root in roots:
					self.parents[root] = biggestRoot
					weight += self.weights.pop(root, 1)

				self.weights[biggestRoot] = weight

			return biggestRoot
		else:
			return self[first]

	def copy(self):
		u = UnionFind()
		u.parents.update(self.parents)
		u.weights.update(self.weights)
		return u

	def dump(self):
		for k, v in self.parents.iteritems():
			print "%r  ->  %r" % (k, v)
