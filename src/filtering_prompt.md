# GPT-4o-mini Question Suitability Filtering Prompt

This prompt was used to classify candidate questions as suitable (`KEEP`) or unsuitable (`REJECT`) for evaluating an LLM's general knowledge.

## System prompt

```text
Decide whether the question is suitable for evaluating an LLM's
general knowledge.

KEEP if BOTH are true:
- It is a normal general-knowledge question that could reasonably be
  asked independently of Wikidata or a database.
- It has a reasonably bounded factual answer that a knowledgeable
  person could reasonably provide.

REJECT if ANY are true:
- It is specific to Wikidata, knowledge graphs, database structure,
  identifiers, properties, ontology, or how information is represented
  in a database.
- It asks for an open-ended or exhaustive set, such as all people with
  a particular name, all buildings in a country, or all people with an
  occupation.
- Its answer depends mainly on what happens to be stored in Wikidata
  rather than on a real-world fact.
- It uses vague database/ontology-like categories such as "entities",
  "items", "instances", or "objects" where there is no clear,
  naturally bounded real-world answer domain.

A question can still involve multiple answers. Reject it only when the
requested answer is unreasonably open-ended, exhaustive, database-defined,
or Wikidata-specific.

When uncertain, REJECT.

Return only:
KEEP
or
REJECT
```

## User prompt

The candidate question is supplied verbatim as the user message, with no additional framing or instructions.

```text
{question}
```

## Output format

The model must return exactly one of the following labels:

- `KEEP`
- `REJECT`
