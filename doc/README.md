# GraphStructQA Documentation

GraphStructQA is a research resource for investigating how the structure of knowledge graphs and SPARQL queries relates to the reliability of large language model (LLM) answers. It brings together 14,729 natural-language questions from the Wikidata Query Logs (WDQL) dataset and WikiWebQuestions, with corresponding SPARQL queries, reference answers, responses from five LLMs, and correctness judgments from two independent LLM evaluators.

A central component of the resource is its set of query and knowledge graph structural features. Query features describe characteristics such as the number of variables, triple patterns, filters, and optional clauses. Knowledge graph features describe the entities and properties referenced by each query, including their connectivity, frequency, entropy, and obscurity. Together, these features support analysis of the conditions under which LLMs answer accurately or produce incorrect or hallucinated responses.

The resource also supports applications beyond analysing the supplied model responses. Users can extract the same features from their own SPARQL queries, identify similar examples through nearest-neighbour search, or train predictive models such as logistic regression to estimate answer reliability. These applications allow the dataset to serve as a basis for further research into feature-based error prediction, query selection, and selective knowledge augmentation.

## Background on feature generation

For methodological background on deriving knowledge graph features,
particularly entropy-based features, and their relationship to LLM answer
correctness, see:

Ushtar Ali, Steven J. Lynden, Akiyoshi Matono, and Toshiyuki Amagasa.
**[When structure predicts hallucination: Aligning LLMs with knowledge graph features](https://doi.org/10.1016/j.datak.2026.102630).**
*Data & Knowledge Engineering*, 165, 102630 (2026).

For the specific features included in GraphStructQA and their computation,
see [Feature descriptions](features.md). To extract these features for your
own SPARQL queries, see the [source documentation](../src/README.md).

The latest feature–accuracy correlation results based on the dataset are available in [`doc/feature_correlations.csv`](../doc/feature_correlations.csv)
and [LaTeX format](../doc/feature_correlations.tex).

