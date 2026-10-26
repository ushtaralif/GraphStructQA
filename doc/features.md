# GraphStructQA Features

Below are the details of all KG structure and SPARQL query-derived features used in this resource. 

## Structural Features

| Feature | Description of the statistic averaged |
|---|---|
| `entity_num_statements_mean` | Number of distinct statement nodes attached to an entity. |
| `entity_num_references_mean` | Number of distinct reference nodes attached to its statements. |
| `entity_num_properties_mean` | Number of distinct claim properties used by an entity. |
| `entity_num_sitelinks_mean` | Number of sitelinks associated with an entity. |
| `entity_num_aliases_mean` | Number of distinct alias literals. |
| `entity_num_languages_mean` | Number of distinct languages represented in labels, aliases, or descriptions. |
| `entity_outgoing_degree_mean` | Number of outgoing direct triples, including triples with literal values. |
| `entity_incoming_degree_mean` | Number of incoming direct triples, capped at 1,000,000 per entity before averaging. |
| `entity_entropy_mean` | Shannon entropy of the distribution of an entity's outgoing direct triples across properties. |
| `entity_obscurity_mean` | Inverse score based on an entity's sitelink and claim-property counts; higher values indicate greater obscurity. |
| `has_property` | Whether the query contains any explicit P-identifiers (1) or none (0); this is a flag rather than a mean. |
| `property_num_triples_mean` | Total number of direct triples using a property in the KG. |
| `property_num_values_mean` | Number of distinct object values for a property. |
| `property_entropy_mean` | Shannon entropy of the distribution of a property's direct triples across object values. |
| `property_num_subjects_mean` | Number of distinct subjects using a property. |
| `property_obscurity_mean` | Inverse score based on the number of subjects using a property; higher values indicate greater obscurity. |

### Notes:

Entropy is computed as `H = -sum(p * log2(p))`, where p is the relative frequency of a property for entity entropy, or an object value for property entropy. Empty distributions have entropy zero.

Entity obscurity is `1 / (1 + ln(1 + sitelinks) + ln(1 + claim_properties))`. Property obscurity is `1 / (1 + ln(1 + subjects))`. These scores and entropies are computed individually before averaging.

Direct-triple statistics use Wikidata's `wdt:` predicates; statement and claim-property counts use `p:` predicates. Structural values depend on the Wikidata snapshot used for extraction.

## Query Features

| Feature | Description |
|---|---|
| `query_num_triple_patterns` | Number of triple and property-path patterns, including patterns within FILTER EXISTS / NOT EXISTS. |
| `query_num_entities` | Number of distinct explicit Q-identifiers in the query. |
| `query_num_properties` | Number of distinct explicit P-identifiers in the query. |
| `query_num_variables` | Number of distinct variable strings in the query. |
| `query_num_optional` | Number of OPTIONAL keywords. |
| `query_num_union` | Number of UNION keywords. |
| `query_num_filter` | Number of FILTER keywords. |
| `query_num_subqueries` | Estimated number of subqueries: SELECT/ASK keyword count minus one, with a minimum of zero. |
| `query_num_aggregates` | Number of aggregate-function occurrences: COUNT, SUM, AVG, MIN, MAX, GROUP_CONCAT, and SAMPLE. |
| `query_num_group_by` | Number of GROUP BY clauses. |
| `query_num_order_by` | Number of ORDER BY clauses. |
| `query_length_chars` | Number of characters in the original SPARQL query. |
| `question_length_words` | Number of whitespace-separated words in the question. |
| `query_is_ask` | Whether the outer query is ASK (1) or not (0). |
| `query_num_computed_values` | Number of Jena extend operators, representing constructs such as BIND and SELECT expressions. |
| `query_num_distinct` | Number of Jena distinct operators. |
| `query_num_limit_offset` | Number of Jena slice operators for LIMIT/OFFSET; both at one query level normally count once. |
| `query_num_property_paths` | Number of property-path operators in the main Jena algebra tree. |
| `query_has_having` | Whether the outer query has a HAVING clause (1) or not (0). |

