"""
Jena query features of the resource (25 of the 86 features)
"""

import argparse
import base64
import csv
import json
import os
import re
import subprocess
import sys
from pathlib import Path

JAVA_SOURCE = r"""// Implementation of the Jena helpers:
//   * query-level flags + algebra, field "jena")
//   * algebra-tree complexity counts (field "complexity")
//   * triple / path / graph-pattern counts (JenaTripleCounter, results/features_v1/jena_triple_comparison.jsonl)
// Input on stdin: "<id>\t<base64 SPARQL>" per line. Output: one JSON object per line.

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.apache.jena.query.*;
import org.apache.jena.sparql.algebra.*;
import org.apache.jena.sparql.algebra.op.*;
import org.apache.jena.sparql.expr.*;
import org.apache.jena.sparql.core.VarExprList;
import org.apache.jena.sparql.lang.sparql_12.ParserSPARQL12;

public class AlgebraFeatures {
    static final class Stats {
        int nodes = 0, leaves = 0, internal = 0, childSum = 0, maxBranch = 0, maxDepth = 0;
        int binary = 0, unary = 0, longestUnary = 0, triples = 0, paths = 0;
        int tcTriples = 0, tcPaths = 0;  // also counting patterns inside FILTER (NOT) EXISTS (JenaTripleCounter)
        long leafDepthSum = 0;
        Map<String, Integer> byName = new TreeMap<>();
    }

    static List<Op> children(Op op) {
        if (op instanceof Op1 o) return List.of(o.getSubOp());
        if (op instanceof Op2 o) return List.of(o.getLeft(), o.getRight());
        if (op instanceof OpN o) return o.getElements();
        return List.of();
    }

    static void countExpr(Expr e, Stats s) {
        if (e == null) return;
        if (e instanceof ExprFunctionOp f) { countPatterns(f.getGraphPattern(), s); }
        if (e instanceof ExprFunction f) for (Expr a : f.getArgs()) countExpr(a, s);
    }

    static void countPatterns(Op op, Stats s) {
        if (op == null) return;
        if (op instanceof OpBGP b) s.tcTriples += b.getPattern().size();
        if (op instanceof OpTriple) s.tcTriples += 1;
        if (op instanceof OpPath) s.tcPaths += 1;
        if (op instanceof OpFilter f) for (Expr e : f.getExprs()) countExpr(e, s);
        if (op instanceof OpExtendAssign ea) { VarExprList v = ea.getVarExprList(); for (var x : v.getVars()) countExpr(v.getExpr(x), s); }
        for (Op c : children(op)) countPatterns(c, s);
    }

    // Parser without the variable-scope validation (fallback only; older Jena versions accepted these queries)
    static final class LenientParser extends ParserSPARQL12 {
        @Override protected void validateParsedQuery(Query q) { }
    }

    // depth: 1 at the root; run = length of the current chain of consecutive unary nodes
    static void walk(Op op, int depth, int run, Stats s) {
        s.nodes++;
        s.byName.merge(op.getName(), 1, Integer::sum);
        s.maxDepth = Math.max(s.maxDepth, depth);
        if (op instanceof OpBGP b) s.triples += b.getPattern().size();
        if (op instanceof OpTriple) s.triples += 1;
        if (op instanceof OpPath) s.paths += 1;
        List<Op> ch = children(op);
        if (ch.isEmpty()) { s.leaves++; s.leafDepthSum += depth; return; }
        s.internal++; s.childSum += ch.size(); s.maxBranch = Math.max(s.maxBranch, ch.size());
        int r;
        if (ch.size() == 1) { s.unary++; r = run + 1; s.longestUnary = Math.max(s.longestUnary, r); }
        else { if (ch.size() == 2) s.binary++; r = 0; }
        for (Op c : ch) walk(c, depth + 1, r, s);
    }

    static String esc(String x) {
        StringBuilder b = new StringBuilder("\"");
        for (char c : x.toCharArray()) {
            switch (c) {
                case '"' -> b.append("\\\""); case '\\' -> b.append("\\\\");
                case '\n' -> b.append("\\n"); case '\r' -> b.append("\\r"); case '\t' -> b.append("\\t");
                default -> { if (c < 0x20) b.append(String.format("\\u%04x", (int) c)); else b.append(c); }
            }
        }
        return b.append('"').toString();
    }

    public static void main(String[] args) throws Exception {
        BufferedReader in = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
        PrintStream out = new PrintStream(new FileOutputStream(FileDescriptor.out), true, "UTF-8");
        String line;
        while ((line = in.readLine()) != null) {
            if (line.isBlank()) continue;
            String[] p = line.split("\t", 2);
            String id = p[0];
            String sparql = new String(Base64.getDecoder().decode(p[1]), StandardCharsets.UTF_8);
            StringBuilder o = new StringBuilder("{\"id\":").append(esc(id));
            try {
                Query q;
                boolean lenient = false;
                try { q = QueryFactory.create(sparql); }
                catch (QueryParseException pe) {
                    if (pe.getMessage() == null || !pe.getMessage().contains("already in-scope")) throw pe;
                    q = new LenientParser().parse(new Query(), sparql); lenient = true;
                }
                Op op = Algebra.compile(q);
                Stats s = new Stats();
                walk(op, 1, 0, s);
                countPatterns(op, s);
                String qt = q.isSelectType() ? "SELECT" : q.isAskType() ? "ASK" : q.isConstructType() ? "CONSTRUCT"
                          : q.isDescribeType() ? "DESCRIBE" : "UNKNOWN";
                o.append(",\"status\":\"ok\",\"queryType\":").append(esc(qt))
                 .append(",\"numVariables\":").append(q.isSelectType() ? q.getResultVars().size() : 0)
                 .append(",\"isDistinct\":").append(q.isDistinct())
                 .append(",\"hasLimit\":").append(q.hasLimit())
                 .append(",\"hasOffset\":").append(q.hasOffset())
                 .append(",\"hasOrderBy\":").append(q.hasOrderBy())
                 .append(",\"hasGroupBy\":").append(q.hasGroupBy())
                 .append(",\"hasHaving\":").append(q.hasHaving())
                 .append(",\"hasValues\":").append(q.hasValues())
                 .append(",\"opClass\":").append(esc(op.getClass().getSimpleName()))
                 .append(",\"algebra\":").append(esc(op.toString()))
                 .append(",\"nodes\":").append(s.nodes).append(",\"leaves\":").append(s.leaves)
                 .append(",\"internal\":").append(s.internal).append(",\"childSum\":").append(s.childSum)
                 .append(",\"maxBranch\":").append(s.maxBranch).append(",\"maxDepth\":").append(s.maxDepth)
                 .append(",\"leafDepthSum\":").append(s.leafDepthSum)
                 .append(",\"binary\":").append(s.binary).append(",\"unary\":").append(s.unary)
                 .append(",\"longestUnary\":").append(s.longestUnary)
                 .append(",\"triples\":").append(s.triples).append(",\"paths\":").append(s.paths)
                 .append(",\"tcTriples\":").append(s.tcTriples).append(",\"tcPaths\":").append(s.tcPaths)
                 .append(",\"lenientParse\":").append(lenient)
                 .append(",\"byName\":{");
                boolean first = true;
                for (var e : s.byName.entrySet()) {
                    if (!first) o.append(','); first = false;
                    o.append(esc(e.getKey())).append(':').append(e.getValue());
                }
                o.append('}');
            } catch (Exception e) {
                o.append(",\"status\":\"error\",\"error\":").append(esc(String.valueOf(e.getMessage())));
            }
            out.println(o.append('}'));
        }
    }
}
"""

PFX = {"p": "http://www.wikidata.org/prop/", "pq": "http://www.wikidata.org/prop/qualifier/",
       "ps": "http://www.wikidata.org/prop/statement/", "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
       "wd": "http://www.wikidata.org/entity/", "wdt": "http://www.wikidata.org/prop/direct/",
       "xsd": "http://www.w3.org/2001/XMLSchema#"}

COLUMNS = [
    "query__triple_pattern_count",
    "algebra__parse_success", "algebra__is_ask", "algebra__jena_num_variables", "algebra__n_nodes",
    "algebra__n_bgp", "algebra__n_join", "algebra__n_filter", "algebra__n_group", "algebra__n_extend",
    "algebra__n_project", "algebra__n_sequence", "algebra__n_distinct", "algebra__n_slice", "algebra__n_paths",
    "algebra__n_subqueries", "algebra__max_depth", "algebra__n_leaves", "algebra__max_branching_factor",
    "algebra__mean_branching_factor", "algebra__n_binary_ops", "algebra__n_unary_ops",
    "algebra__longest_unary_chain", "algebra__jena_has_group_by", "algebra__jena_has_having",
]
FLOAT_COLUMNS = {"algebra__parse_success", "algebra__is_ask", "algebra__mean_branching_factor",
                 "algebra__jena_has_group_by", "algebra__jena_has_having"}


def load_questions(paths, id_prefix="", ids_from=None):
    rows = []
    for p in paths:
        text = Path(p).read_text(encoding="utf-8")
        recs = json.loads(text) if text.lstrip().startswith("[") else [json.loads(l) for l in text.split("\n") if l.strip()]
        rows += [{**r, "id": id_prefix + r["id"]} for r in recs]
    if ids_from:
        keep = {json.loads(l)["id"] for l in open(ids_from, encoding="utf-8") if l.strip()}
        rows = [r for r in rows if r["id"] in keep]
    assert len({r["id"] for r in rows}) == len(rows), "duplicate ids"
    return rows


def with_prefixes(q):
    if re.search(r"^\s*PREFIX\b", q, re.I | re.M):
        return q
    body = re.sub(r'"[^"]*"|<[^>]*>', " ", q)
    used = sorted(p for p in PFX if re.search(rf"(?<![\w?$]){p}:", body))
    return "".join(f"PREFIX {p}: <{PFX[p]}>\n" for p in used) + q


def run_jena(rows, jena_home, work_dir):
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    cp_lib = str(Path(jena_home) / "lib" / "*")
    src = work / "AlgebraFeatures.java"
    if not (work / "AlgebraFeatures.class").exists() or src.read_text() != JAVA_SOURCE:
        src.write_text(JAVA_SOURCE)
        subprocess.run(["javac", "-proc:none", "-cp", cp_lib, "-d", str(work), str(src)], check=True)
    stdin = "".join(r["id"] + "\t" + base64.b64encode(with_prefixes(r["sparql"]).encode()).decode() + "\n" for r in rows)
    out = subprocess.run(["java", "-cp", f"{work}{os.pathsep}{cp_lib}", "AlgebraFeatures"], input=stdin.encode(),
                         stdout=subprocess.PIPE, check=True).stdout.decode("utf-8")
    return {j["id"]: j for j in map(json.loads, out.splitlines())}


def features(j):
    n = j["byName"]
    proj = n.get("project", 0)
    return {
        "query__triple_pattern_count": j["tcTriples"] + j["tcPaths"],
        "algebra__parse_success": 1.0,
        "algebra__is_ask": 1.0 if j["queryType"] == "ASK" else 0.0,
        "algebra__jena_num_variables": j["numVariables"],
        "algebra__n_nodes": j["nodes"], "algebra__n_bgp": n.get("bgp", 0), "algebra__n_join": n.get("join", 0),
        "algebra__n_filter": n.get("filter", 0), "algebra__n_group": n.get("group", 0),
        "algebra__n_extend": n.get("extend", 0), "algebra__n_project": proj,
        "algebra__n_sequence": n.get("sequence", 0), "algebra__n_distinct": n.get("distinct", 0),
        "algebra__n_slice": n.get("slice", 0), "algebra__n_paths": j["paths"],
        "algebra__n_subqueries": proj - (1 if j["opClass"] == "OpProject" else 0),
        "algebra__max_depth": j["maxDepth"], "algebra__n_leaves": j["leaves"],
        "algebra__max_branching_factor": j["maxBranch"],
        "algebra__mean_branching_factor": j["childSum"] / j["internal"] if j["internal"] else 0.0,
        "algebra__n_binary_ops": j["binary"], "algebra__n_unary_ops": j["unary"],
        "algebra__longest_unary_chain": j["longestUnary"],
        "algebra__jena_has_group_by": float(j["hasGroupBy"]), "algebra__jena_has_having": float(j["hasHaving"]),
    }


def fmt(col, v):
    return repr(float(v)) if col in FLOAT_COLUMNS else str(int(v))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", nargs="+", required=True, help="JSON/JSONL files with id, sparql")
    ap.add_argument("--id-prefix", default="", help="prefix added to the input ids (WDQL: wdql_)")
    ap.add_argument("--ids-from", default=None, help="keep only ids in this JSONL")
    ap.add_argument("--jena-home", default=os.environ.get("JENA_HOME"), help="Apache Jena 6.2.0 (default $JENA_HOME)")
    ap.add_argument("--work-dir", default=".jena_build")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    if not args.jena_home:
        sys.exit("set --jena-home or JENA_HOME")

    rows = load_questions(args.input, args.id_prefix, args.ids_from)
    out = run_jena(rows, args.jena_home, args.work_dir)
    failed = [r["id"] for r in rows if out[r["id"]]["status"] != "ok"]
    if failed:
        sys.exit(f"Jena could not parse {len(failed)} queries, e.g. {failed[:5]}")
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id"] + COLUMNS)
        for r in rows:
            v = features(out[r["id"]])
            w.writerow([r["id"]] + [fmt(c, v[c]) for c in COLUMNS])
    print(f"{len(rows):,} questions, {len(COLUMNS)} Jena features -> {args.output}")


if __name__ == "__main__":
    main()
