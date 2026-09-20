// Tests for the query layer. These pin the behaviours that were regressions
// once already, so a future change to the grammar or the scope rules has to
// say out loud that it is changing them.
//
// Run: node --test
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  classValue, parseQuery, parseTerm, applyFilters, preparePeaks,
  scopedRoutes, easiestRoute, ROUTE_COL_LABEL, didYouMean
} from "./search.mjs";

const PEAKS = JSON.parse(readFileSync(new URL("./peaks.json", import.meta.url), "utf8"));
preparePeaks(PEAKS);

const NOTHING = { summits: new Map(), planned: new Map() };
const q = (s, tracked = NOTHING) => applyFilters(PEAKS, parseQuery(s), tracked);
const listed = s => q(s).filter(p => !p.subpoint);
const names = rows => rows.map(p => p.name).sort();
const keyOf = p => p.view_route && p.view_route.route_key;

test("class ordinal ignores the modifier words", () => {
  // Easy Class 3 cannot sit below 3, so Difficult Class 2 must not sit above 2.
  assert.equal(classValue("Class 2"), 2);
  assert.equal(classValue("Difficult Class 2"), 2);
  assert.equal(classValue("Easy Class 3"), 3);
  assert.equal(classValue("Difficult Class 2 Moderate Snow"), 2);
  assert.equal(classValue("no class here"), null, "unparseable fails every comparison");
});

test("rating values prefix-match", () => {
  assert.equal(parseTerm("exposure:mod").value, 2);
  assert.equal(parseTerm("commitment:cons").value, 3);
  assert.equal(parseTerm("exposure:nope").bad, true);
});

test("an unknown field stays plain text rather than matching everything", () => {
  const parsed = parseQuery("bogus:7");
  assert.equal(parsed.terms.length, 0);
  assert.deepEqual(parsed.tokens, ["bogus", "7"]);
});

test("a half-typed term constrains nothing, a broken one matches nothing", () => {
  assert.equal(listed("class:").length, 58, "class: is not a term yet");
  assert.equal(q("class:>").length, 58, "53 ranked plus the 5 unranked with routes");
  assert.equal(q("kind:bogus").length, 0, "a value that cannot parse matches nothing");
});

test("the default view is the 58 peaks with routes, on their standard routes", () => {
  const rows = q("");
  assert.equal(rows.length, 58, "53 ranked plus the 5 unranked peaks with routes");
  assert.equal(rows.filter(p => p.subpoint).length, 0, "subpoints need a text token");
  assert.ok(rows.every(p => p.view_route === p.standard),
    "nothing may repoint the columns without a scope");
  assert.equal(ROUTE_COL_LABEL[parseQuery("").scope], "Standard");
});

test("kind:combo class:<=4 drops the peaks whose only combo is Class 5", () => {
  // The bug this whole line of work started from: kind: used to be an
  // existence test, so these six passed on their standard route's class.
  const got = names(listed("kind:combo class:<=4"));
  for (const n of ["Crestone Needle", "Crestone Peak", "Maroon Peak",
                   "North Maroon Peak", "Little Bear Peak"]) {
    assert.ok(!got.includes(n), `${n} has no combo at Class 4 or easier`);
  }
  // Blanca has two combos; the Class 3 one qualifies, so it stays, and the
  // column has to describe that one rather than the Class 5 traverse.
  const blanca = listed("kind:combo class:<=4").find(p => p.name === "Blanca Peak");
  assert.ok(blanca, "Blanca qualifies on Combo: Blanca and Ellingwood");
  assert.equal(blanca.view_route.difficulty, "Class 3");
});

test("kind:combo class:<=2 is exactly the peaks with a Class 2 or easier combo", () => {
  // Cameron and Conundrum are unranked, and both have a Class 2 combo
  // (the Decalibron, Castle-Conundrum). They belong here now that the list
  // is the 58.
  assert.deepEqual(names(listed("kind:combo class:<=2")), [
    "Castle Peak", "Conundrum Peak", "Grays Peak", "Missouri Mountain",
    "Mount Belford", "Mount Bross", "Mount Cameron", "Mount Columbia",
    "Mount Democrat", "Mount Harvard", "Mount Lincoln", "Mount Oxford",
    "Torreys Peak"
  ]);
});

test("one route has to satisfy every route field, not one route per field", () => {
  // Ellingwood Point used to match by taking the class from South Face
  // (Class 2, road 6) and the road from North Ridge (Class 3, road 1).
  const got = names(listed("scope:any class:<=2 road:<=1"));
  assert.ok(!got.includes("Ellingwood Point"));
  assert.ok(got.includes("Mount Elbert"), "genuine single-route matches survive");
  for (const p of listed("scope:any class:<=2 road:<=1")) {
    assert.ok(classValue(p.view_route.difficulty) <= 2, p.name);
    assert.ok(p.view_route.road <= 1, p.name);
  }
});

test("a narrowed scope still excludes peaks with no route of that kind", () => {
  const withCombo = new Set(PEAKS.filter(p => p.combo_routes.length).map(p => p.peak_id));
  assert.equal(withCombo.size, 24);
  assert.ok(q("kind:combo").every(p => withCombo.has(p.peak_id)));
  assert.equal(scopedRoutes(PEAKS.find(p => p.name === "Mount Elbert"), "combo").length, 0,
    "no fallback to the standard route, or the exclusion stops working");
});

test("kind outranks scope when both are present", () => {
  const parsed = parseQuery("scope:any kind:combo");
  assert.equal(parsed.scope, "combo");
  assert.equal(parsed.kind, "combo");
  assert.deepEqual(names(listed("scope:any kind:combo class:<=4")),
                   names(listed("kind:combo class:<=4")));
});

test("an explicit kind narrows the text search too", () => {
  // "hourglass" is in Little Bear's West Ridge and Hourglass summit route,
  // so no combo contains it and the row must not claim one does.
  assert.equal(q("hourglass kind:combo").length, 0);
  assert.equal(q("south face kind:combo").length, 0);
  assert.equal(q("ellingwood arete kind:combo").length, 0);
  // Words that really are on a combo still land, including via its summits.
  assert.deepEqual(names(q("el diente kind:combo")), ["El Diente Peak", "Mount Wilson"]);
  assert.deepEqual(names(q("crestone kind:combo")), ["Crestone Needle", "Crestone Peak"]);
});

test("without a kind the text search stays wider than the filters", () => {
  // These are reachable only through non-standard routes, so scoping text to
  // the predicate pool would take every one of them to zero.
  for (const [query, count] of [["decalibron", 4], ["sawtooth", 2],
                                ["tour de abyss", 2], ["ellingwood arete", 1],
                                ["hourglass", 1], ["lake como", 3]]) {
    assert.equal(q(query).length, count, query);
  }
});

test("an unranked peak with routes is listed; a route-less subpoint needs its name", () => {
  assert.deepEqual(names(q("").filter(p => p.unranked)),
    ["Challenger Point", "Conundrum Peak", "El Diente Peak", "Mount Cameron", "North Eolus"]);
  // Having routes means having something to filter on, so these answer terms.
  assert.ok(q("kind:combo").some(p => p.name === "El Diente Peak"));
  assert.ok(q("class:<=3").some(p => p.name === "North Eolus"));
  assert.ok(q("summited:no").some(p => p.unranked));
  // The 15 with an empty routes array stay out until they are named.
  const subpoint = p => p.name === "North Massive";
  assert.ok(!q("").some(subpoint));
  assert.ok(!q("summited:no").some(subpoint), "a term must not surface a subpoint");
  assert.ok(q("north massive").some(subpoint));
});

test("rows are peaks, so a shared route fills several of them", () => {
  const rows = listed("kind:combo");
  assert.equal(rows.length, 24);
  assert.equal(new Set(rows.map(keyOf)).size, 11, "counted by route_key, not by object");
  // Grays and Torreys hold two separate objects that are both torr5.
  const grays = rows.find(p => p.name === "Grays Peak");
  const torreys = rows.find(p => p.name === "Torreys Peak");
  assert.equal(keyOf(grays), keyOf(torreys));
  assert.notEqual(grays.view_route, torreys.view_route, "same key, different objects");
  const app = listed("kind:approach");
  assert.equal(app.length, 12);
  assert.equal(new Set(app.map(keyOf)).size, 4);
});

test("the columns describe the easiest route that cleared the bar", () => {
  // Bross under scope:any class:<=2: the pool offers West Slopes first
  // (Class 2, score 2.0292), but East Slopes is Class 1 at score 1. Asking
  // for Class 2 or easier should show the easiest way that clears the bar,
  // not whichever route build_data.py happened to sort first.
  const bross = listed("scope:any class:<=2").find(p => p.name === "Mount Bross");
  assert.equal(bross.view_route.name, "Mt. Bross - East Slopes");
  assert.equal(bross.view_route.difficulty, "Class 1");
  const qualifying = bross.pool.filter(r => classValue(r.difficulty) <= 2);
  assert.ok(qualifying.length > 1);
  assert.notEqual(bross.view_route, qualifying[0], "and not merely the first that qualified");
  assert.equal(bross.view_score, Math.min(...qualifying.map(r => r.score)));
});

test("the columns describe the easiest qualifying route", () => {
  const blueSky = listed("kind:combo").find(p => p.name === "Mount Blue Sky");
  const combos = blueSky.combo_routes;
  assert.ok(combos.length > 1, "Blue Sky has more than one combo to choose between");
  assert.equal(blueSky.view_score, Math.min(...combos.map(r => r.score)));
  assert.equal(easiestRoute(combos), combos.find(r => r.score === blueSky.view_score));
});

test("the row names the route when it is not the standard one", () => {
  for (const p of listed("kind:combo")) {
    assert.equal(p.scope_hit, p.view_route);
    assert.equal(p.view_road, p.view_route.road);
  }
  assert.ok(q("").every(p => p.scope_hit === null));
});

test("summited and planned read the tracked sets they are handed", () => {
  const elbert = PEAKS.find(p => p.name === "Mount Elbert");
  const tracked = { summits: new Map([[elbert.peak_id, {}]]), planned: new Map() };
  assert.deepEqual(names(q("summited:yes", tracked)), ["Mount Elbert"]);
  assert.equal(q("summited:yes", NOTHING).length, 0);
  assert.equal(q("summited:no", tracked).length, 57, "58 listed peaks less the summited one");
});

test("did-you-mean corrects across every route, not just the scoped ones", () => {
  assert.deepEqual(didYouMean(PEAKS, parseQuery("sneffles").tokens), null,
    "an alias already resolves, so there is nothing to correct");
  assert.deepEqual(didYouMean(PEAKS, parseQuery("elbert").tokens), null);
  assert.equal(didYouMean(PEAKS, parseQuery("zzzzzz").tokens), null);
  assert.deepEqual(didYouMean(PEAKS, parseQuery("decalibrom").tokens), ["decalibron"]);
});
