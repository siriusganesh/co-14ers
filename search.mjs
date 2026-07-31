// Query layer for the peak table: tokenizing, the field grammar, route
// scoping and the filter itself. Everything here is pure -- it takes the peak
// list and the tracked summits/planned sets as arguments rather than reaching
// for the page's globals -- so search.test.mjs can exercise it directly.
//
// index.html does not import this file. scripts/embed_data.py inlines it
// between the SEARCH MODULE markers so the page still loads in one request,
// dropping only the export block below. Run `python3 scripts/embed_data.py`
// after editing, and `python3 scripts/embed_data.py --check` verifies the two
// copies agree.

function normalizeSearch(s) {
  return (s || "").toLowerCase()
    .replace(/[.,'\u2019+\/()\-&:]/g, " ")
    .replace(/\bmt\b/g, "mount")
    .replace(/\s+/g, " ")
    .trim();
}

// Hand-curated aliases, expanded per token after normalization. Kept
// deliberately small: renames the data cannot know about, plus the
// misspellings that actually get typed. Values may be multi-word; keys
// must be single tokens.
const SEARCH_ALIASES = {
  evans: "blue sky",      // renamed Mount Evans -> Mount Blue Sky, 2023
  bells: "maroon",        // "the Bells" -> Maroon Peak / North Maroon
  sneffles: "sneffels",
  quandry: "quandary",
  bierstat: "bierstadt",
  wetterhorne: "wetterhorn"
};

function queryTokens(q) {
  const norm = normalizeSearch(q);
  if (!norm) return [];
  return norm.split(" ").flatMap(t => {
    const alias = SEARCH_ALIASES[t];
    return alias ? normalizeSearch(alias).split(" ") : [t];
  });
}

function classNumber(diff) {
  const m = diff && diff.match(/Class\s*(\d)/i);
  return m ? parseInt(m[1], 10) : 99;
}
// Class as a filterable number. The modifier words do not move it:
// "Difficult Class 2" is 2 and "Easy Class 3" is 3, because the words
// qualify a class rather than sitting between two of them -- Easy Class 3
// cannot be less than 3, so Difficult Class 2 must not be more than 2.
// Returns null rather than classNumber()'s 99 sentinel, so a route with no
// parseable class fails every comparison instead of satisfying class:>=N.
function classValue(diff) {
  const n = classNumber(diff);
  return n === 99 ? null : n;
}

// ---- structured query grammar -------------------------------------------
// Field terms are parsed out of the same input as the text search, so
// "traverse commitment:high" is one query. Text and terms are ANDed.

const RATING_ORDER = { low: 1, moderate: 2, considerable: 3, high: 4, extreme: 5 };
const RATING_HINT = "low, moderate, considerable, high, extreme";

function ratingValue(v) {
  const n = RATING_ORDER[String(v || "").toLowerCase()];
  return n == null ? null : n;
}
function ratingName(n) {
  return Object.keys(RATING_ORDER).find(k => RATING_ORDER[k] === n) || String(n);
}
// Distances arrive as "9.75 mi" and gains as "4,500'".
function routeMiles(v) { const m = String(v || "").match(/([\d.]+)/); return m ? parseFloat(m[1]) : null; }
function routeGain(v) { const m = String(v || "").replace(/,/g, "").match(/(\d+)/); return m ? parseInt(m[1], 10) : null; }

function compareValue(actual, op, want) {
  if (actual == null) return false;
  if (op === ">")  return actual >  want;
  if (op === ">=") return actual >= want;
  if (op === "<")  return actual <  want;
  if (op === "<=") return actual <= want;
  return actual === want;
}

function parseNumberValue(raw) {
  const n = parseFloat(raw);
  return isNaN(n) ? null : n;
}
function parseRatingValue(raw) {
  // Prefix match, so "mod" and "cons" work.
  const key = Object.keys(RATING_ORDER).find(k => k.startsWith(raw.toLowerCase()));
  return key ? RATING_ORDER[key] : null;
}
function parseBoolValue(raw) {
  const v = raw.toLowerCase();
  if (["yes", "y", "true", "1"].includes(v)) return true;
  if (["no", "n", "false", "0"].includes(v)) return false;
  return null;
}
function parseKindValue(raw) {
  return ["route", "combo", "approach"].find(k => k.startsWith(raw.toLowerCase())) || null;
}

function ratingField(key) {
  return {
    scope: "route", parse: parseRatingValue, format: ratingName, hint: RATING_HINT,
    test: (r, t) => compareValue(ratingValue(r[key]), t.op, t.value)
  };
}

const QUERY_FIELDS = {
  class: {
    scope: "route", parse: parseNumberValue, hint: "1, 2, 3, 4, 5",
    test: (r, t) => compareValue(classValue(r.difficulty), t.op, t.value)
  },
  exposure: ratingField("exposure"),
  rockfall: ratingField("rockfall"),
  routefinding: ratingField("route_finding"),
  commitment: ratingField("commitment"),
  road: {
    scope: "route", parse: parseNumberValue, hint: "0 paved to 6 difficult 4WD",
    test: (r, t) => compareValue(r.road, t.op, t.value)
  },
  dist: {
    scope: "route", parse: parseNumberValue, hint: "miles",
    test: (r, t) => compareValue(routeMiles(r.distance), t.op, t.value)
  },
  gain: {
    scope: "route", parse: parseNumberValue, hint: "feet",
    test: (r, t) => compareValue(routeGain(r.gain), t.op, t.value)
  },
  range: {
    scope: "peak", parse: raw => normalizeSearch(raw) || null, hint: "sawatch, sangre, elk, ...",
    test: (p, t) => p.search_range.includes(t.value)
  },
  // Snow is peak-level on purpose: a snow line is a property of the peak's
  // route list, not of its standard route. kind used to sit here as the same
  // shape of existence test, which made "kind:combo class:<=4" mean "has a
  // combo, and its standard route is Class 4 or easier" -- six peaks whose
  // only combo is Class 5 passed that, showing their standard route's class.
  // It is a scope modifier now; see SCOPE_FIELD and scopedRoutes.
  snow: {
    scope: "peak", parse: parseBoolValue, format: v => (v ? "yes" : "no"), hint: "yes, no",
    test: (p, t) => p.has_snow === t.value
  },
  summited: {
    scope: "peak", parse: parseBoolValue, format: v => (v ? "yes" : "no"), hint: "yes, no",
    test: (p, t, tracked) => tracked.summits.has(p.peak_id) === t.value
  },
  planned: {
    scope: "peak", parse: parseBoolValue, format: v => (v ? "yes" : "no"), hint: "yes, no",
    test: (p, t, tracked) => tracked.planned.has(p.peak_id) === t.value
  }
};

// Spellings that reach the same field. Keys are compared with separators
// stripped, so "route-finding" and "route_finding" already land on
// "routefinding" before this map is consulted.
const FIELD_ALIASES = {
  rf: "routefinding", finding: "routefinding",
  exp: "exposure", rock: "rockfall", commit: "commitment",
  distance: "dist", miles: "dist", mi: "dist",
  vert: "gain", elevationgain: "gain",
  difficulty: "class", grade: "class",
  type: "kind", routetype: "kind",
  done: "summited", todo: "planned"
};

// scope and kind are modifiers rather than predicates: they select which
// routes the route-scoped fields are tested against, and so which route the
// Standard and Road columns describe. They live in the grammar so the query
// string is the whole filter state and one string restores a view.
//
// kind is the narrower of the two and wins when both are present: it names an
// exact pool, while scope only says how wide to go. So "scope:any kind:combo"
// tests combos, not everything.
const SCOPE_FIELD = {
  scope: "modifier", hint: "any, standard",
  parse: raw => (["any", "standard"].find(v => v.startsWith(raw.toLowerCase())) || null)
};
const KIND_FIELD = {
  scope: "modifier", hint: "route, combo, approach",
  parse: parseKindValue
};
const MODIFIER_FIELDS = { scope: SCOPE_FIELD, kind: KIND_FIELD };

const OP_LABEL = { "=": ":", ">=": "≥", "<=": "≤", ">": ">", "<": "<" };

// Splits one word into field, comparator and value. Returns null when the
// word is not a recognized field term, in which case it stays plain text --
// an unknown field must not silently match everything.
function parseTerm(word) {
  const m = word.match(/^([A-Za-z][A-Za-z_-]*):(.*)$/);
  if (!m) return null;
  const key = m[1].toLowerCase().replace(/[-_]/g, "");
  const name = (QUERY_FIELDS[key] || MODIFIER_FIELDS[key]) ? key : FIELD_ALIASES[key];
  const spec = MODIFIER_FIELDS[name] || (name && QUERY_FIELDS[name]);
  if (!spec) return null;
  const rest = m[2].match(/^(>=|<=|>|<|=)?(.*)$/);
  const op = rest[1] || "=";
  const rawValue = rest[2].trim();
  // "class:" and "class:>" are what a half-typed term looks like. Treating
  // them as a broken term blanks the table for the three keystrokes before
  // the value lands, so an empty value means "not a term yet": no chip, no
  // constraint. Only a non-empty value that fails to parse is an error.
  // Carries the field even while incomplete, so a control writing a term
  // for the same field can replace a half-typed one.
  if (!rawValue) return { incomplete: true, field: name, raw: word };
  const value = spec.parse(rawValue);
  const term = { field: name, spec, op, value, raw: word };
  if (value == null) {
    term.bad = true;
    term.label = `${name} ${OP_LABEL[op]} ${rawValue || "?"}`;
    term.reason = `expects ${spec.hint}`;
  } else {
    const shown = spec.format ? spec.format(value) : String(value);
    term.label = `${name} ${OP_LABEL[op]} ${shown}`;
  }
  return term;
}

// One pass over the raw input: field terms out, everything else into the
// text tokens from the name/route/trailhead search.
function parseQuery(raw) {
  const terms = [];
  const text = [];
  (raw || "").split(/\s+/).filter(Boolean).forEach(word => {
    const term = parseTerm(word);
    if (term && term.incomplete) return;      // half-typed, ignore for now
    if (term) terms.push(term); else text.push(word);
  });
  const kindTerm = terms.find(t => t.field === "kind" && !t.bad);
  const scopeTerm = terms.find(t => t.field === "scope" && !t.bad);
  // kind carried separately as well as folded into scope, because an empty
  // pool means different things: no route of the requested kind (exclude the
  // peak) versus a peak with no routes at all.
  return {
    terms,
    tokens: queryTokens(text.join(" ")),
    kind: kindTerm ? kindTerm.value : null,
    scope: kindTerm ? kindTerm.value : (scopeTerm ? scopeTerm.value : "standard")
  };
}

function relevanceScore(p, tokens) {
  if (!tokens.length) return 0;
  if (p.search_name.startsWith(tokens[0])) return 0;
  if (tokens.every(t => p.search_name.includes(t))) return 1;
  if (tokens.every(t => p.search_primary.includes(t))) return 2;
  if (p.search_pool.some(r => tokens.every(t => r.search_name.includes(t)))) return 3;
  return 4;
}

// Every word in the data, for the did-you-mean fallback. Built once, and only
// ever read when a query returns nothing.
let SEARCH_VOCAB = null;
function searchVocab(peaks) {
  if (SEARCH_VOCAB) return SEARCH_VOCAB;
  const set = new Set();
  peaks.forEach(p => p.search_text.split(" ").forEach(w => { if (w.length > 2) set.add(w); }));
  SEARCH_VOCAB = [...set];
  return SEARCH_VOCAB;
}
// True when one insertion, deletion or substitution turns a into b. Cheaper
// and easier to read than a full edit-distance matrix, and one edit covers
// the misspellings people actually type.
function withinOneEdit(a, b) {
  if (a === b) return true;
  const d = a.length - b.length;
  if (d > 1 || d < -1) return false;
  if (d === 0) {
    let diff = 0;
    for (let i = 0; i < a.length; i++) if (a[i] !== b[i] && ++diff > 1) return false;
    return diff === 1;
  }
  const [long, short] = d === 1 ? [a, b] : [b, a];
  let i = 0, j = 0, skipped = false;
  while (i < long.length && j < short.length) {
    if (long[i] === short[j]) { i++; j++; continue; }
    if (skipped) return false;
    skipped = true; i++;
  }
  return true;
}
// The single closest correction for a query that matched nothing, or null.
// Only the tokens that appear nowhere are candidates for replacement.
function didYouMean(peaks, tokens) {
  if (!tokens.length) return null;
  const vocab = searchVocab(peaks);
  const fixed = tokens.map(t => {
    if (vocab.some(w => w.includes(t))) return t;
    const hit = vocab.find(w => withinOneEdit(t, w));
    return hit || t;
  });
  if (fixed.join(" ") === tokens.join(" ")) return null;
  const anyMatch = peaks.some(p => fixed.every(t => p.search_text.includes(t)));
  return anyMatch ? fixed : null;
}

// Routes a route-scoped predicate may look at, and the routes the Standard
// and Road columns may describe. Default is the standard route, which is what
// the class and road dropdowns have always tested. The "any route" chip
// widens it to every way up the peak; approaches stay out of that pool, since
// a Class 1 approach hike says nothing about the summit.
//
// A kind narrows to exactly that kind, with no fallback to the standard
// route. The empty pool is load-bearing: it is what makes kind:combo still
// exclude the 49 peaks with no combo, now that kind is a modifier rather than
// an existence test.
function scopedRoutes(p, scope) {
  if (scope === "route")    return p.summit_routes;
  if (scope === "combo")    return p.combo_routes;
  if (scope === "approach") return p.approach_routes;
  if (scope !== "any") return p.standard ? [p.standard] : [];
  const pool = p.summit_routes.concat(p.combo_routes);
  return pool.length ? pool : (p.standard ? [p.standard] : []);
}
// Which of several qualifying routes the columns describe: the easiest, by
// build_data.py's composite score. If you asked for class:<=3 you want the
// easiest way that clears the bar, not whichever route the build script
// happened to sort first. Ties keep pool order, so the standard route wins
// one against a combo of equal score.
function easiestRoute(list) {
  return list.reduce((best, r) =>
    (r.score != null ? r.score : 99) < (best.score != null ? best.score : 99) ? r : best);
}
// Header for the difficulty column, keyed by scope. render() only reaches for
// it once a row is actually showing something other than its standard route:
// scope:any with no route predicate still lands every row on the standard
// route, and "Route" there would advertise a widening that changed nothing.
const ROUTE_COL_LABEL = {
  standard: "Standard", any: "Route", route: "Route",
  combo: "Combo", approach: "Approach"
};

// Derived fields every query and every row reads: the route buckets, the
// standard route, the composite fallbacks and the search haystacks. Called
// once at startup, never per keystroke.
function preparePeaks(peaks) {
  peaks.forEach(p => {
    // Summit routes only. Combos and approaches are listed separately in
    // the detail panel and shouldn't inflate a peak's route count.
    p.summit_routes = p.routes.filter(r => r.kind === "route");
    p.combo_routes = p.routes.filter(r => r.kind === "combo");
    p.approach_routes = p.routes.filter(r => r.kind === "approach");
    p.route_count = p.summit_routes.length;
    // Prefer the route that is both standard and primary. build_data.py's
    // sort already puts it first, but a peak's list also carries combos
    // flagged standard (the Decalibron is Bross's standard), so say it
    // outright rather than relying on the sort.
    const std = p.summit_routes.find(r => r.is_standard) || p.summit_routes[0]
      || p.routes.find(r => r.is_standard) || p.routes[0];
    p.standard = std || null;
    // Composite score from build_data.py: class stays dominant, the four
    // risk ratings only order peaks within a class bucket. See the
    // difficulty_score() comment in scripts/build_data.py for the formula.
    // The column and its sort read view_score / view_road, which applyFilters
    // sets from the route the active scope picked; these two are the fallback
    // for a peak with no routes at all.
    p.standard_score = std && std.score != null ? std.score : 99;
    p.standard_road = std && std.road != null ? std.road : 99;
    p.has_snow = p.routes.some(r => r.is_snow_climb);
    // Precomputed search haystacks. Search used to test p.name and p.range
    // only, which left everything else in the data unreachable: 138 route
    // names, 12 combos, 7 approaches and 70 trailheads. Queries like
    // "traverse", "decalibron", "couloir" and "lake como" all returned
    // nothing despite being present. Built once here because applyFilters
    // runs on every keystroke.
    //
    // The per-token test in applyFilters walks p.search_pool rather than the
    // joined p.search_text, so it can respect a kind:. p.search_text is what
    // the did-you-mean vocabulary and its any-match check still read, and
    // those stay deliberately unscoped: a correction should be offered for a
    // word that sits on a route the current scope filtered out.
    p.routes.forEach(r => {
      r.search_name = normalizeSearch(r.name);
      r.search_th = normalizeSearch(r.trailhead || "");
      r.search_text = normalizeSearch([r.name, r.summits, r.trailhead, r.difficulty, r.kind].join(" "));
    });
    // Name, slug and range alone, so render() can tell a route-only match
    // from a direct hit and label the row accordingly.
    p.search_primary = normalizeSearch([p.name, p.slug, p.range].join(" "));
    p.search_range = normalizeSearch(p.range);
    p.search_name = normalizeSearch(p.name);
    p.search_text = [p.search_primary].concat(p.routes.map(r => r.search_text)).join(" ");
  });
}

function applyFilters(peaks, parsed, tracked) {
  const { tokens, terms } = parsed;
  // A term that failed to parse matches nothing, so it is settled once here
  // rather than re-tested against all 73 peaks.
  if (terms.some(t => t.bad)) return [];
  // Split once instead of per peak. Route-scoped terms have to be handled as
  // a group, not one at a time -- see the qualifying pool below.
  const peakTerms  = terms.filter(t => t.spec.scope === "peak");
  const routeTerms = terms.filter(t => t.spec.scope === "route");
  return peaks.filter(p => {
    // Pool first: the text test, the relevance tier, the row's match hint and
    // the route predicates all read it, so nothing downstream can disagree
    // with the scope.
    p.pool = scopedRoutes(p, parsed.scope);
    // Routes the text search may match. An explicit kind: is a statement about
    // what you are looking for, so a token has to be accounted for by a route
    // of that kind. "hourglass kind:combo" used to return Little Bear, because
    // "hourglass" sits in its West Ridge summit route, and the row then
    // credited the Blanca traverse for a word no combo contains.
    //
    // Without a kind the search stays wide, and deliberately wider than the
    // route predicates: text is the only way to reach a non-standard route at
    // all. Narrowing this to p.pool measured as "decalibron", "sawtooth",
    // "tour de abyss" and "ellingwood arete" all going from hits to zero.
    p.search_pool = parsed.kind ? p.pool : p.routes;
    p.relevance = relevanceScore(p, tokens);
    // The route the difficulty and road columns describe, and the route their
    // sort reads. The standard route until a scope sends it elsewhere. Reset
    // for every peak so a stale pick from a previous keystroke cannot leak
    // into the row.
    p.view_route = p.standard;
    // Set when that route is not the standard one, so the row can name it.
    p.scope_hit = null;
    // Unranked summits (El Diente, Challenger Point, Conundrum, Cameron
    // and 16 others) stay out of the default list, but they are real peaks
    // in the data and were unreachable by any query because this test ran
    // before the search test. A text token brings them back, grouped
    // separately by render() so the ranked count stays honest.
    //
    // Text tokens only, not terms: now that the selects and chips write
    // terms, gating on terms too would mean clicking "hide summited"
    // surfaced all 20 subpoints. The rule is that you search for a subpoint
    // by name; filters describe the ranked list.
    if (p.unranked && !tokens.length) return false;
    // Every token must appear somewhere in the peak's own name, slug or range,
    // or on one route in the search pool. AND across tokens, not one substring
    // test against a joined string, so word order and extra words in between
    // do not matter: "elbert northeast" hits, and "little bear hourglass" can
    // take one token from the peak and one from a route.
    //
    // Identical to the old single test against p.search_text whenever there is
    // no kind: to narrow the pool, since a token never contains the space that
    // joined those haystacks and so can never straddle two of them.
    if (tokens.length && !tokens.every(t => p.search_primary.includes(t)
        || p.search_pool.some(r => r.search_text.includes(t)))) return false;
    for (const term of peakTerms) if (!term.spec.test(p, term, tracked)) return false;

    // An empty pool under a narrowed scope means the peak has no route of
    // that kind. This is the existence test kind: used to perform itself.
    if (parsed.kind && !p.pool.length) return false;
    if (routeTerms.length) {
      // One route has to satisfy every route-scoped term. Testing each term
      // against the pool on its own let two different routes cover two
      // terms: "scope:any class:<=2 road:<=1" matched Ellingwood Point on
      // South Face for the class (road 6) and North Ridge for the road
      // (Class 3), describing a trip that does not exist.
      const qualifying = p.pool.filter(r => routeTerms.every(t => t.spec.test(r, t)));
      if (!qualifying.length) return false;
      p.view_route = easiestRoute(qualifying);
    } else if (p.pool.length) {
      // No route predicate to qualify on, but a narrowed scope still decides
      // which route the columns describe. Prefer the standard route when the
      // pool holds it, so the default view is unchanged.
      p.view_route = p.pool.includes(p.standard) ? p.standard : easiestRoute(p.pool);
    }
    if (p.view_route && p.view_route !== p.standard) p.scope_hit = p.view_route;
    p.view_score = p.view_route && p.view_route.score != null ? p.view_route.score : p.standard_score;
    p.view_road  = p.view_route && p.view_route.road  != null ? p.view_route.road  : p.standard_road;
    return true;
  });
}

export {
  normalizeSearch, queryTokens, classNumber, classValue,
  ratingValue, ratingName, routeMiles, routeGain, compareValue,
  QUERY_FIELDS, FIELD_ALIASES, MODIFIER_FIELDS, parseTerm, parseQuery,
  relevanceScore, searchVocab, withinOneEdit, didYouMean,
  scopedRoutes, easiestRoute, ROUTE_COL_LABEL,
  preparePeaks, applyFilters
};
