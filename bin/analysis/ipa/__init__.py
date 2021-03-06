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

from analysis.cpa import simpleimagebuilder
from . entrypointbuilder import buildEntryPoint
from . dump import Dumper

from . ipanalysis import IPAnalysis

from . memory.extractorpolicy import ExtractorPolicy
from . memory.storegraphpolicy import DefaultStoreGraphPolicy

def dumpAnalysisResults(analysis):
	dumper = Dumper('summaries/ipa')

	dumper.index(analysis.contexts.values(), analysis.root)

	for context in analysis.contexts.itervalues():
		dumper.dumpContext(context)


def evaluateWithImage(compiler, prgm):
	with compiler.console.scope('ipa analysis'):
		analysis = IPAnalysis(compiler, prgm.storeGraph.canonical, ExtractorPolicy(compiler.extractor), DefaultStoreGraphPolicy(prgm.storeGraph))
		analysis.trace = True

		for ep, args in prgm.entryPoints:
			buildEntryPoint(analysis, ep, args)

		for i in range(5):
			analysis.topDown()
			analysis.bottomUp()

		print "%5d code" % len(analysis.liveCode)
		print "%5d contexts" % len(analysis.contexts)
		print "%.2f ms decompile" % (analysis.decompileTime*1000.0)

	with compiler.console.scope('ipa dump'):
		dumpAnalysisResults(analysis)


def evaluate(compiler, prgm):
	simpleimagebuilder.build(compiler, prgm)
	result = evaluateWithImage(compiler, prgm)
	return result
