"""PC 원본 리포트 ↔ 웹(GitHub Pages) 리포트 일치 검증 — 독립 검증 도구.

같은 회차의 리포트가 두 곳에 있다.

    PC 원본   <저장소>/reports/toto_<회차>.html          (`_write_report()` 가 쓴다)
    웹        <저장소>-pages/reports/toto_<회차>.html    (`--publish-round` 가 복사한다)
              또는 이미 push 한 `origin/gh-pages` 의 같은 경로

**파일 해시만으로 판정하지 않는다.** 해시가 달라도 내용은 같을 수 있다 —
대표적으로 윈도우에서는 원본이 CRLF 로 쓰이고, gh-pages 에 커밋할 때 Git 의
`autocrlf` 가 LF 로 바꿔 저장한다(실측 260054: push 된 판은 LF 뿐이다).
그래서 네 단계로 본다.

    A  파일      크기 · SHA-256 · 줄바꿈/BOM 을 걷은 SHA · head 구조(meta·style·script)
    B  내용      화면에 나오는 글자와 수를 경기·블록별로 뽑아 비교한다.
                 수는 **값으로** 비교한다 ("1.20" = "1.2", 1.20 ≠ 1.25)
    C  브라우저  실제로 렌더한 DOM 의 글자(접힌 영역 포함)를 경기별로 비교한다
    S  원본 자료  Panel Result · 회차 저장본의 값이 두 HTML 에 그대로 있는가

차이는 네 갈래로 나눈다 — A 표현/레이아웃 · B 배포용 구조 · C 실제 데이터 ·
D 분석 내용. **C·D 가 하나라도 있으면 FAIL** 이다. A·B 는 보고만 한다.

사용:

    python tools/verify_web_report.py 260054
    python tools/verify_web_report.py                  # 양쪽에 다 있는 가장 최근 회차
    python tools/verify_web_report.py 260054 --web-ref origin/gh-pages   # push 된 판
    python tools/verify_web_report.py --original A.html --web B.html
    python tools/verify_web_report.py 260054 --no-browser --no-source

종료코드  0 PASS · 1 FAIL · 2 검증할 수 없음(파일 없음 등)

**읽기만 한다.** 리포트·저장본·gh-pages 어느 것도 쓰지 않고, git 은 읽기
명령(`show`·`ls-tree`)만 부른다. 분석 코드(`toto/`)의 값을 다시 계산하지
않는다 — 원본 자료 대조(S)는 저장된 값을 읽어 HTML 에 있는지만 본다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from html.parser import HTMLParser
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

PUBLISH_NAME = re.compile(r"^toto_(\d+)\.html$")

# 차이 분류 (§9 원칙 2)
LAYOUT, DEPLOY, DATA, ANALYSIS = "A", "B", "C", "D"
KIND_KO = {LAYOUT: "A. 표현/레이아웃 차이", DEPLOY: "B. 배포용 HTML 구조 차이",
           DATA: "C. 실제 데이터 차이", ANALYSIS: "D. 실제 분석 내용 차이"}
BLOCKING = {DATA, ANALYSIS}

# 내용 갈래 — 보고서의 [핵심 데이터 비교] 줄과 같다
CATEGORIES = (("count", "경기 수"), ("order", "경기 순서"),
              ("teams", "홈팀/원정팀"), ("score", "예측 스코어"),
              ("analyst", "분석가 의견"), ("moderator", "사회자 종합"),
              ("evidence", "Evidence ID"), ("data", "핵심 수치"),
              ("market", "시장 기준값"), ("page", "머리글·기타 문구"))
CAT_KO = dict(CATEGORIES, render="브라우저 렌더 글자")

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}
NO_TEXT = {"script", "style", "noscript", "template"}
# 화면·보조기술에 보이는 속성 — 내용이다
CONTENT_ATTRS = ("aria-label", "title", "alt")
# 링크·앵커 — 배포 때 바뀔 수 있다 (B)
LINK_ATTRS = ("href", "id", "src")

EVIDENCE_ID = re.compile(r"^E\d+$")
_TOKEN = re.compile(
    r"(?P<num>(?<![\w.])[-+−]?\d{1,3}(?:,\d{3})+(?:\.\d+)?(?![\w.])"
    r"|(?<![\w.])[-+−]?\d+(?:\.\d+)?)"
    r"|(?P<word>[^\W\d_]\w*)"
    r"|(?P<sym>\S)")


# ==========================================================================
# 파싱 — 표준 라이브러리만 쓴다
# ==========================================================================
class Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag: str, attrs=None, parent=None):
        self.tag, self.attrs = tag, dict(attrs or {})
        self.children: list = []
        self.parent = parent

    @property
    def classes(self) -> set:
        return set((self.attrs.get("class") or "").split())

    def iter(self):
        yield self
        for c in self.children:
            if isinstance(c, Node):
                yield from c.iter()

    def text(self) -> str:
        out: list = []
        _collect_text(self, out)
        return norm_space(" ".join(out))


def _collect_text(node: Node, out: list) -> None:
    for c in node.children:
        if isinstance(c, str):
            out.append(c)
        elif c.tag not in NO_TEXT:
            _collect_text(c, out)


class _Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#document")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, [(k, v or "") for k, v in attrs], self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        node = Node(tag, [(k, v or "") for k, v in attrs], self.stack[-1])
        self.stack[-1].children.append(node)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def parse_html(text: str) -> Node:
    b = _Builder()
    b.feed(text)
    b.close()
    return b.root


def norm_space(s: str) -> str:
    return " ".join(unicodedata.normalize("NFC", s).split())


@dataclass(frozen=True)
class Tok:
    kind: str          # "n" 수 · "t" 글자
    value: object      # Decimal 또는 str
    raw: str

    @property
    def key(self):
        return (self.kind, self.value)


def to_number(raw: str) -> Decimal | None:
    try:
        return Decimal(raw.replace("−", "-").replace(",", ""))
    except InvalidOperation:
        return None


def tokenize(text: str) -> list[Tok]:
    out = []
    for m in _TOKEN.finditer(unicodedata.normalize("NFC", text)):
        raw = m.group(0)
        if m.lastgroup == "num":
            val = to_number(raw)
            if val is not None:
                out.append(Tok("n", val, raw))
                continue
        out.append(Tok("t", raw, raw))
    return out


# ==========================================================================
# 내용 추출 — 경기 · 블록 · 갈래
# ==========================================================================
@dataclass
class Segment:
    key: tuple
    match: int | None
    cat: str
    texts: list = field(default_factory=list)
    links: list = field(default_factory=list)
    geometry: list = field(default_factory=list)
    _toks: list | None = None

    @property
    def toks(self) -> list[Tok]:
        if self._toks is None:
            self._toks = tokenize(" ".join(self.texts))
        return self._toks

    @property
    def label(self) -> str:
        return " · ".join(str(k) for k in self.key[2:] if k != "")


@dataclass
class Doc:
    name: str
    raw: bytes
    root: Node
    segments: dict = field(default_factory=dict)       # key → Segment (삽입 순서)
    match_order: list = field(default_factory=list)    # 상세 카드 순서
    overview_order: list = field(default_factory=list)
    title: str = ""
    head: dict = field(default_factory=dict)
    json_blobs: list = field(default_factory=list)
    body_scripts: list = field(default_factory=list)


_MATCH_ID = re.compile(r"^match-(\d+)$")
_HREF_MATCH = re.compile(r"^#match-(\d+)$")


def _seg(doc: Doc, key: tuple, match, cat) -> Segment:
    seg = doc.segments.get(key)
    if seg is None:
        seg = doc.segments[key] = Segment(key, match, cat)
    return seg


def _first_child(node: Node, tag: str) -> Node | None:
    for c in node.children:
        if isinstance(c, Node) and c.tag == tag:
            return c
    return None


def _block_cat(title: str) -> str:
    if title.startswith("Pinnacle"):
        return "market"
    if title.startswith("패널 분석"):
        return "panel"
    return "data"


def _panel_sub_cat(label: str) -> str:
    if "스코어 흐름" in label:
        return "score"
    if "Pinnacle" in label:
        return "market"
    return "moderator"


class _Walker:
    """문서를 한 번 훑으며 글자를 (경기, 블록, 갈래) 자리에 나눠 담는다."""

    def __init__(self, doc: Doc):
        self.doc = doc
        self.dup: dict = {}

    def run(self) -> None:
        html = next((n for n in self.doc.root.iter() if n.tag == "html"),
                    self.doc.root)
        head = _first_child(html, "head")
        if head is not None:
            self._head(head)
        body = _first_child(html, "body") or html
        ctx = {"match": None, "scope": "page", "block": "", "sub": "",
               "cat": "page"}
        self._walk(body, ctx)

    # -- head ---------------------------------------------------------------
    def _head(self, head: Node) -> None:
        metas, styles, scripts, links = [], [], [], []
        for n in head.iter():
            if n.tag == "title":
                self.doc.title = n.text()
            elif n.tag == "meta":
                metas.append(tuple(sorted(n.attrs.items())))
            elif n.tag == "style":
                styles.append(_sha("".join(c for c in n.children
                                           if isinstance(c, str))))
            elif n.tag == "script":
                self._script(n, scripts)
            elif n.tag == "link":
                links.append(tuple(sorted(n.attrs.items())))
        self.doc.head = {"meta": metas, "style": styles, "script": scripts,
                         "link": links}

    def _script(self, n: Node, into: list) -> None:
        body = "".join(c for c in n.children if isinstance(c, str))
        typ = (n.attrs.get("type") or "").lower()
        if "json" in typ:
            try:
                self.doc.json_blobs.append(json.loads(body))
            except ValueError:
                self.doc.json_blobs.append({"unparsed": body})
        else:
            into.append((n.attrs.get("src", ""), _sha(body)))

    # -- body ---------------------------------------------------------------
    def _key(self, ctx: dict) -> tuple:
        base = (ctx["scope"], ctx["match"], ctx["block"], ctx["sub"])
        return base

    def _walk(self, node: Node, ctx: dict) -> None:
        for child in node.children:
            if isinstance(child, str):
                if child.strip():
                    self._seg(ctx).texts.append(child)
                continue
            self._enter(child, ctx)

    def _seg(self, ctx: dict) -> Segment:
        return _seg(self.doc, self._key(ctx), ctx["match"], ctx["cat"])

    def _attrs(self, n: Node, ctx: dict) -> None:
        seg = None
        for a in CONTENT_ATTRS:
            v = n.attrs.get(a)
            if v and v.strip():
                seg = seg or self._seg(ctx)
                seg.texts.append(f" {v} ")
        for a, v in n.attrs.items():
            if a.startswith("data-") and v.strip():
                seg = seg or self._seg(ctx)
                seg.texts.append(f" {v} ")
        link = tuple((a, n.attrs[a]) for a in LINK_ATTRS if a in n.attrs)
        rest = tuple(sorted((a, v) for a, v in n.attrs.items()
                            if a not in CONTENT_ATTRS and a not in LINK_ATTRS
                            and not a.startswith("data-")))
        if link or rest:
            seg = seg or self._seg(ctx)
            if link:
                seg.links.append((n.tag,) + link)
            seg.geometry.append((n.tag,) + rest)

    def _enter(self, n: Node, ctx: dict) -> None:
        if n.tag in ("script", "noscript", "template"):
            if n.tag == "script":
                self._script(n, self.doc.body_scripts)
            return
        if n.tag == "style":
            self.doc.head.setdefault("body_style", []).append(
                _sha("".join(c for c in n.children if isinstance(c, str))))
            return
        cls, nid = n.classes, n.attrs.get("id", "")
        m = _MATCH_ID.match(nid)
        if n.tag == "article" and m:
            no = int(m.group(1))
            self.doc.match_order.append(no)
            ctx = dict(ctx, match=no, scope="match", block="(카드 머리)",
                       sub="", cat="data")
        elif n.tag == "a" and "sumcard" in cls:
            hm = _HREF_MATCH.match(n.attrs.get("href", ""))
            no = int(hm.group(1)) if hm else len(self.doc.overview_order) + 1
            self.doc.overview_order.append(no)
            ctx = dict(ctx, match=no, scope="overview", block="(요약 카드)",
                       sub="", cat="data")
        elif nid == "match-overview":
            ctx = dict(ctx, scope="overview-intro", block="", sub="",
                       cat="page")
        elif n.tag == "div" and "block" in cls:
            h4 = _first_child(n, "h4")
            title = h4.text() if h4 is not None else "(제목 없음)"
            dkey = (ctx["scope"], ctx["match"], title)
            self.dup[dkey] = self.dup.get(dkey, 0) + 1
            if self.dup[dkey] > 1:
                title = f"{title} #{self.dup[dkey]}"
            cat = _block_cat(title)
            ctx = dict(ctx, block=title, sub="",
                       cat="moderator" if cat == "panel" else cat)
            if cat == "panel":
                self._attrs(n, ctx)
                self._panel(n, dict(ctx, cat="data", sub="(설명)"))
                return
        elif ctx["scope"] == "match" and n.tag == "h3":
            ctx = dict(ctx, sub="팀", cat="teams")
        elif ctx["scope"] == "overview" and "tm" in cls:
            ctx = dict(ctx, sub="팀", cat="teams")
        elif ctx["scope"] == "overview" and cls & {"sumscore", "init", "sumlab"}:
            ctx = dict(ctx, sub="스코어", cat="score")
        elif "mscore" in cls:        # 앞의 라벨과 다른 자리여야 갈래가 섞이지 않는다
            ctx = dict(ctx, sub="종합 스코어 값", cat="score")
        elif "pscore" in cls:
            ctx = dict(ctx, sub=ctx["sub"].replace("분석가 ", "스코어 "), cat="score")
        self._attrs(n, ctx)
        self._walk(n, ctx)

    def _panel(self, block: Node, ctx: dict) -> None:
        """패널 블록 — `p.lbl` 이 뒤따르는 형제들의 갈래를 정한다."""
        for child in block.children:
            if isinstance(child, str):
                if child.strip():
                    self._seg(ctx).texts.append(child)
                continue
            cls = child.classes
            if child.tag == "p" and "lbl" in cls:
                label = child.text()
                ctx = dict(ctx, sub=label, cat=_panel_sub_cat(label))
            if child.tag == "div" and "traits" in cls:
                for card in child.children:
                    if not isinstance(card, Node):
                        continue
                    h5 = _first_child(card, "h5")
                    who = h5.text() if h5 is not None else "(분석가)"
                    cctx = dict(ctx, sub=f"분석가 {who}", cat="analyst")
                    self._attrs(card, cctx)
                    for part in card.children:
                        if isinstance(part, str):
                            if part.strip():
                                self._seg(cctx).texts.append(part)
                        else:
                            self._enter(part, cctx)
                continue
            self._enter(child, ctx)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def load_doc(name: str, raw: bytes) -> Doc:
    # HTML 파서는 입력의 CRLF·CR 을 LF 로 바꾼 뒤 읽는다 (HTML 표준 전처리).
    # 같게 해 두어야 `<style>` 해시가 줄바꿈 때문에 달라 보이지 않는다.
    text = raw.decode("utf-8-sig", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    doc = Doc(name, raw, parse_html(text))
    _Walker(doc).run()
    return doc


# ==========================================================================
# 비교
# ==========================================================================
@dataclass
class Finding:
    kind: str                 # A/B/C/D
    what: str
    match: int | None = None
    cat: str = ""
    where: str = ""
    original: str = ""
    web: str = ""
    doc: str = ""             # 원본 자료 대조에서만 — 어느 HTML 인가
    labels: tuple = ("PC 원본", "웹 리포트")


SOURCE_LABELS = ("원본 자료", "HTML")


def _snippet(toks: list[Tok], lo: int, hi: int, limit=24) -> str:
    part = toks[lo:hi]
    s = " ".join(t.raw for t in part[:limit])
    return s + (" …" if len(part) > limit else "") if part else "(없음)"


def _context(toks: list[Tok], lo: int, n=8) -> str:
    return " ".join(t.raw for t in toks[max(0, lo - n):lo])


SHORT = 16      # 이만큼 짧은 자리(스코어·팀 이름)는 조각이 아니라 통째로 보여 준다


def _kind(seg: Segment, numeric: bool) -> str:
    """수가 바뀌면 데이터(C), 분석가·사회자 문장이 바뀌면 분석 내용(D)."""
    return ANALYSIS if seg.cat in ("analyst", "moderator") and not numeric else DATA


def compare_tokens(seg_o: Segment, seg_w: Segment) -> tuple[list, int]:
    """(차이 목록, 숫자 표기만 다른 개수)."""
    a, b = seg_o.toks, seg_w.toks
    ka, kb = [t.key for t in a], [t.key for t in b]
    fmt_only = 0
    if ka == kb:
        fmt_only = sum(1 for x, y in zip(a, b) if x.raw != y.raw)
        return [], fmt_only
    if len(a) <= SHORT and len(b) <= SHORT:
        numeric = ([t.kind for t in a] == [t.kind for t in b]
                   and [t.value for t in a if t.kind == "t"]
                   == [t.value for t in b if t.kind == "t"])
        return [Finding(_kind(seg_o, numeric), "값이 다름" if numeric else "내용이 다름",
                        seg_o.match, seg_o.cat, seg_o.label,
                        _snippet(a, 0, len(a)), _snippet(b, 0, len(b)))], fmt_only
    out = []
    sm = SequenceMatcher(None, ka, kb, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            fmt_only += sum(1 for x, y in zip(a[i1:i2], b[j1:j2]) if x.raw != y.raw)
            continue
        numeric = all(t.kind == "n" for t in a[i1:i2] + b[j1:j2])
        kind = _kind(seg_o, numeric)
        if seg_o.cat == "page" and op == "insert":
            kind = DEPLOY           # 원본에 없는 문구를 웹이 **덧붙이기만** 했다
        what = ("값이 다름" if numeric else
                {"replace": "내용이 다름", "delete": "웹에서 빠짐",
                 "insert": "웹에만 있음"}[op])
        where = seg_o.label
        ctx = _context(a, i1)
        if ctx:
            where += f" — 앞 문맥: …{ctx}"
        out.append(Finding(kind, what, seg_o.match, seg_o.cat, where,
                           _snippet(a, i1, i2), _snippet(b, j1, j2)))
    return out, fmt_only


def compare_docs(o: Doc, w: Doc) -> dict:
    findings: list[Finding] = []
    fmt_only = 0
    cat_status = {k: "PASS" for k, _ in CATEGORIES}
    present = {k: False for k, _ in CATEGORIES}
    present["count"] = present["order"] = True

    # 경기 수 · 순서
    if len(o.match_order) != len(w.match_order) or \
            len(o.overview_order) != len(w.overview_order):
        findings.append(Finding(
            DATA, "경기 수가 다름", cat="count",
            original=f"상세 {len(o.match_order)} · 요약 {len(o.overview_order)}",
            web=f"상세 {len(w.match_order)} · 요약 {len(w.overview_order)}"))
    if o.match_order != w.match_order or o.overview_order != w.overview_order:
        findings.append(Finding(
            DATA, "경기 순서가 다름", cat="order",
            original=f"{o.match_order} / 요약 {o.overview_order}",
            web=f"{w.match_order} / 요약 {w.overview_order}"))

    # 제목
    if o.title != w.title:
        findings.append(Finding(DATA, "문서 제목이 다름", cat="page",
                                where="<title>", original=o.title, web=w.title))

    # 블록 목록과 내용
    keys_o, keys_w = list(o.segments), list(w.segments)
    for key in keys_o:
        so = o.segments[key]
        if any(t.kind == "t" and EVIDENCE_ID.match(t.value) for t in so.toks):
            present["evidence"] = True
        present[so.cat] = present[so.cat] or bool(so.toks)
        sw = w.segments.get(key)
        if sw is None:
            if so.toks:
                findings.append(Finding(
                    ANALYSIS if so.cat in ("analyst", "moderator") else DATA,
                    "웹 리포트에 이 자리가 없음", so.match, so.cat, so.label,
                    _snippet(so.toks, 0, len(so.toks)), "(없음)"))
            continue
        diffs, n = compare_tokens(so, sw)
        findings.extend(diffs)
        fmt_only += n
        if so.links != sw.links:
            findings.append(Finding(DEPLOY, "링크·앵커가 다름", so.match, so.cat,
                                    so.label, str(so.links[:3]), str(sw.links[:3])))
        if so.geometry != sw.geometry:
            findings.append(Finding(LAYOUT, "도형·스타일 속성이 다름", so.match,
                                    so.cat, so.label))
    for key in keys_w:
        if key in o.segments:
            continue
        sw = w.segments[key]
        if not sw.toks:
            continue
        kind = DEPLOY if sw.cat == "page" else (
            ANALYSIS if sw.cat in ("analyst", "moderator") else DATA)
        findings.append(Finding(kind, "웹 리포트에만 있는 자리", sw.match, sw.cat,
                                sw.label, "(없음)", _snippet(sw.toks, 0, len(sw.toks))))

    # Evidence ID — 경기별 순서 그대로
    for no in sorted(set(o.match_order) | set(w.match_order)):
        eo = _evidence_ids(o, no)
        ew = _evidence_ids(w, no)
        if eo != ew:
            findings.append(Finding(DATA, "Evidence ID 목록이 다름", no, "evidence",
                                    "경기 카드 전체", " ".join(eo[:30]),
                                    " ".join(ew[:30])))

    # head · 스크립트 · 내장 JSON
    for part, kind in (("meta", DEPLOY), ("script", DEPLOY), ("link", DEPLOY),
                       ("style", LAYOUT), ("body_style", LAYOUT)):
        if o.head.get(part, []) != w.head.get(part, []):
            findings.append(Finding(kind, f"<{part.replace('body_', '')}> 가 다름",
                                    cat="page", where="head",
                                    original=f"{len(o.head.get(part, []))}개",
                                    web=f"{len(w.head.get(part, []))}개"))
    if o.body_scripts != w.body_scripts:
        findings.append(Finding(DEPLOY, "본문 <script> 가 다름", cat="page",
                                original=f"{len(o.body_scripts)}개",
                                web=f"{len(w.body_scripts)}개"))
    if o.json_blobs != w.json_blobs:
        findings.append(Finding(DATA, "내장 JSON 이 다름", cat="page",
                                original=f"{len(o.json_blobs)}개",
                                web=f"{len(w.json_blobs)}개"))

    for f in findings:
        if f.kind in BLOCKING and f.cat in cat_status:
            cat_status[f.cat] = "FAIL"
    for k in cat_status:
        if cat_status[k] == "PASS" and not present.get(k):
            cat_status[k] = "해당 없음"
    return {"findings": findings, "fmt_only": fmt_only, "cat_status": cat_status}


def _evidence_ids(doc: Doc, no: int) -> list:
    out = []
    for seg in doc.segments.values():
        if seg.key[0] == "match" and seg.match == no:
            out.extend(t.value for t in seg.toks
                       if t.kind == "t" and EVIDENCE_ID.match(t.value))
    return out


# ==========================================================================
# A. 파일
# ==========================================================================
def normalize_bytes(raw: bytes) -> bytes:
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    return raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def file_stage(o: bytes, w: bytes) -> dict:
    no, nw = normalize_bytes(o), normalize_bytes(w)
    return {
        "size": (len(o), len(w)),
        "sha": (hashlib.sha256(o).hexdigest(), hashlib.sha256(w).hexdigest()),
        "identical": o == w,
        "same_after_newline": no == nw,
        "crlf": (o.count(b"\r\n"), w.count(b"\r\n")),
        "bom": (o.startswith(b"\xef\xbb\xbf"), w.startswith(b"\xef\xbb\xbf")),
        "lines_changed": _changed_lines(no, nw),
    }


def _changed_lines(a: bytes, b: bytes) -> int:
    la, lb = a.split(b"\n"), b.split(b"\n")
    if la == lb:
        return 0
    sm = SequenceMatcher(None, la, lb, autojunk=False)
    return sum(max(i2 - i1, j2 - j1) for op, i1, i2, j1, j2 in sm.get_opcodes()
               if op != "equal")


# ==========================================================================
# C. 브라우저
# ==========================================================================
_JS = """() => {
  const SKIP = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE"]);
  function all(root) {
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const out = []; let n;
    while ((n = w.nextNode())) {
      let p = n.parentElement, skip = false;
      while (p) { if (SKIP.has(p.tagName)) { skip = true; break; } p = p.parentElement; }
      if (!skip) out.push(n.nodeValue);
    }
    return out.join(" ");
  }
  const cards = [...document.querySelectorAll("article.match")]
    .map(a => ({id: a.id, all: all(a), shown: a.innerText}));
  const over = [...document.querySelectorAll("a.sumcard")]
    .map(a => ({id: a.getAttribute("href"), all: all(a), shown: a.innerText}));
  return {title: document.title, cards, over,
          overflow: document.documentElement.scrollWidth > window.innerWidth};
}"""


def browser_stage(o_raw: bytes, w_raw: bytes, widths=(1200, 400)) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"status": "SKIP", "reason": "playwright 가 설치되어 있지 않습니다"}
    tmp = Path(tempfile.mkdtemp(prefix="verify_web_report_"))
    try:
        po, pw = tmp / "original.html", tmp / "web.html"
        po.write_bytes(o_raw)
        pw.write_bytes(w_raw)
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch()
            except Exception as exc:                      # noqa: BLE001
                return {"status": "SKIP",
                        "reason": f"브라우저를 띄우지 못했습니다: {exc}".splitlines()[0]}
            try:
                return _browser_compare(browser, po, pw, widths)
            finally:
                browser.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _render(browser, path: Path, width: int) -> dict:
    page = browser.new_page(viewport={"width": width, "height": 900})
    page.route("**/*", lambda r: r.continue_()
               if r.request.url.startswith("file:") else r.abort())
    page.goto(path.as_uri(), wait_until="load")
    data = page.evaluate(_JS)
    page.close()
    return data


def _browser_compare(browser, po: Path, pw: Path, widths) -> dict:
    findings, info = [], {}
    base_o = base_w = None
    for width in widths:
        do, dw = _render(browser, po, width), _render(browser, pw, width)
        info[width] = {"cards": (len(do["cards"]), len(dw["cards"])),
                       "overflow": (do["overflow"], dw["overflow"])}
        if base_o is None:
            base_o, base_w = do, dw
        for group in ("cards", "over"):
            for i, (a, b) in enumerate(zip(do[group], dw[group])):
                if [t.key for t in tokenize(a["all"])] != \
                        [t.key for t in tokenize(b["all"])]:
                    findings.append(Finding(
                        DATA, "렌더된 글자(접힌 영역 포함)가 다름",
                        _card_no(a["id"], i), "render", f"{width}px {a['id']}"))
                elif [t.key for t in tokenize(a["shown"])] != \
                        [t.key for t in tokenize(b["shown"])]:
                    findings.append(Finding(
                        LAYOUT, "화면에 펼쳐 보이는 글자만 다름 (CSS 표시 차이)",
                        _card_no(a["id"], i), "render", f"{width}px {a['id']}"))
            if len(do[group]) != len(dw[group]):
                findings.append(Finding(DATA, f"렌더된 {group} 수가 다름", cat="count",
                                        where=f"{width}px",
                                        original=str(len(do[group])),
                                        web=str(len(dw[group]))))
        if do["title"] != dw["title"]:
            findings.append(Finding(DATA, "렌더된 제목이 다름", cat="page",
                                    original=do["title"], web=dw["title"]))
        if dw["overflow"] and not do["overflow"]:
            findings.append(Finding(LAYOUT, "웹 리포트에만 가로 넘침", cat="page",
                                    where=f"{width}px"))
    status = "FAIL" if any(f.kind in BLOCKING for f in findings) else "PASS"
    return {"status": status, "findings": findings, "info": info}


def _card_no(ident: str, i: int) -> int:
    m = re.search(r"(\d+)$", ident or "")
    return int(m.group(1)) if m else i + 1


# ==========================================================================
# S. 원본 자료 ↔ HTML
# ==========================================================================
def _panel_parts(doc: Doc, no: int) -> dict:
    """경기 카드의 패널 블록에서 역할별 글자·스코어·근거를 읽는다."""
    card = next((n for n in doc.root.iter() if n.tag == "article"
                 and n.attrs.get("id") == f"match-{no:02d}"), None)
    out = {"analysts": {}, "mscore": None, "moderator_text": ""}
    if card is None:
        return out
    block = next((n for n in card.iter() if n.tag == "div" and "block" in n.classes
                  and (_first_child(n, "h4") is not None)
                  and _first_child(n, "h4").text().startswith("패널 분석")), None)
    if block is None:
        return out
    after_moderator = []
    seen_lbl = False
    for child in block.children:
        if not isinstance(child, Node):
            continue
        if "traits" in child.classes:
            for c in child.children:
                if isinstance(c, Node):
                    h5 = _first_child(c, "h5")
                    out["analysts"][h5.text() if h5 is not None else ""] = c
            continue
        if child.tag == "p" and "lbl" in child.classes and "사회자" in child.text():
            seen_lbl = True
        if child.tag == "p" and "mscore" in child.classes:
            out["mscore"] = child.text()
        if seen_lbl:
            after_moderator.append(child.text())
    out["moderator_text"] = norm_space(" ".join(after_moderator))
    return out


def _score_text(home, away) -> str:
    return "없음" if home is None or away is None else f"{home} : {away}"


def source_stage(round_id: str, docs: list[Doc], *, base: Path | None = None
                 ) -> dict:
    base = base or REPO
    findings, checked = [], []
    pr = base / "panel_results" / f"{round_id}_panel_result.json"
    if pr.is_file():
        checked.append(f"Panel Result ({pr.name})")
        data = json.loads(pr.read_text(encoding="utf-8-sig"))
        try:
            from toto.panel import ROLE_KO
        except Exception:                                    # noqa: BLE001
            ROLE_KO = {"data_analyst": "데이터 분석가",
                       "matchup_tactical_analyst": "맞대결·전술 분석가"}
        for m in data.get("matches", []):
            no = m.get("match_number")
            if not isinstance(no, int) or m.get("panel_status") == "생략":
                continue
            for doc in docs:
                findings += _check_panel(doc, no, m, ROLE_KO)
    art = base / "data" / "artifacts" / f"{round_id}.json"
    if art.is_file():
        try:
            from toto import artifact
            report, why = artifact.load_path(art)
        except Exception as exc:                            # noqa: BLE001
            report, why = None, str(exc)
        if report is None:
            findings.append(Finding(DATA, f"회차 저장본을 읽지 못했습니다: {why}",
                                    cat="market", labels=SOURCE_LABELS))
        else:
            checked.append(f"회차 저장본 ({art.name})")
            for match in report.matches:
                for doc in docs:
                    findings += _check_market(doc, match)
    if not checked:
        return {"status": "SKIP", "reason": "원본 자료(panel_results · "
                "data/artifacts)가 이 저장소에 없습니다", "findings": []}
    status = "FAIL" if any(f.kind in BLOCKING for f in findings) else "PASS"
    return {"status": status, "checked": checked, "findings": findings}


def _cited_ids(card: Node) -> list:
    """`인용한 근거 E001, E014` 줄의 ID 만 읽는다.

    분석가 문장 안에도 `xG 2.56(E014)` 처럼 ID 가 나오는데 그것은 **문장 속
    언급**이지 `evidence_ids` 가 아니다. 카드 전체에서 뽑으면 둘이 섞여 같은
    자료를 다르다고 판정한다 (실물 260054 의 맞대결 분석가 카드가 그랬다).
    """
    line = next((n.text() for n in card.iter() if "vs" in n.classes
                 and n.text().startswith("인용한 근거")), "")
    return [t.value for t in tokenize(line) if t.kind == "t"
            and EVIDENCE_ID.match(t.value)]


def _src(kind, what, no, cat, where, doc, original="", web="") -> Finding:
    return Finding(kind, what, no, cat, where, original, web, doc.name,
                   SOURCE_LABELS)


def _check_panel(doc: Doc, no: int, m: dict, role_ko: dict) -> list:
    out = []
    parts = _panel_parts(doc, no)
    where = "패널 블록"
    for role in ("data_analyst", "matchup_tactical_analyst"):
        op = m.get(role)
        if not isinstance(op, dict):
            continue
        card = parts["analysts"].get(role_ko.get(role, role))
        if card is None:
            out.append(_src(ANALYSIS, "원본 자료의 분석가 의견이 HTML 에 없음",
                            no, "analyst", where, doc, role, "(없음)"))
            continue
        text = card.text()
        want = _score_text(op.get("predicted_home"), op.get("predicted_away"))
        pscore = next((n.text() for n in card.iter() if "pscore" in n.classes), "")
        if not pscore.endswith(want):
            out.append(_src(DATA, "분석가 예상 스코어가 원본 자료와 다름", no,
                            "score", where, doc, want, pscore))
        for piece in [op.get("summary", "")] + list(op.get("rationale") or []):
            if piece and norm_space(piece) not in text:
                out.append(_src(ANALYSIS, "분석가 문장이 원본 자료와 다름", no,
                                "analyst", where, doc, norm_space(piece)[:80],
                                "(HTML 에서 찾지 못함)"))
        ids = _cited_ids(card)
        if ids != list(op.get("evidence_ids") or []):
            out.append(_src(DATA, "분석가 Evidence ID 가 원본 자료와 다름", no,
                            "evidence", f"{where} · {role_ko.get(role, role)}",
                            doc, " ".join(op.get("evidence_ids") or []) or "(없음)",
                            " ".join(ids) or "(없음)"))
    mod = m.get("moderator")
    if isinstance(mod, dict):
        want = _score_text(mod.get("adopted_home"), mod.get("adopted_away"))
        got = parts["mscore"]
        if want != "없음" and got != want:
            out.append(_src(DATA, "사회자 채택 스코어가 원본 자료와 다름", no,
                            "score", where, doc, want, str(got)))
        conclusion = norm_space(mod.get("conclusion") or "")
        if conclusion and conclusion not in parts["moderator_text"]:
            out.append(_src(ANALYSIS, "사회자 결론 문장이 원본 자료와 다름", no,
                            "moderator", where, doc, conclusion[:80],
                            "(HTML 에서 찾지 못함)"))
    return out


def _check_market(doc: Doc, match) -> list:
    """Pinnacle 블록 표의 배당·내재확률이 저장본 값과 같은가 (표시 반올림 허용)."""
    if match.probs is None or match.odds.home is None:
        return []
    card = next((n for n in doc.root.iter() if n.tag == "article"
                 and n.attrs.get("id") == f"match-{match.no:02d}"), None)
    if card is None:
        return [_src(DATA, "경기 카드가 없음", match.no, "market", "경기 카드", doc)]
    block = next((n for n in card.iter() if n.tag == "div" and "block" in n.classes
                  and _first_child(n, "h4") is not None
                  and _first_child(n, "h4").text().startswith("Pinnacle")), None)
    if block is None:
        return [_src(DATA, "시장 기준선 블록이 없음", match.no, "market", "경기 카드",
                     doc)]
    rows = {}
    for tr in (n for n in block.iter() if n.tag == "tr"):
        cells = [c.text() for c in tr.children if isinstance(c, Node) and c.tag == "td"]
        if len(cells) >= 3:
            rows[cells[0]] = cells[1:3]
    out = []
    want = {"승": (match.odds.home, match.probs.home),
            "무": (match.odds.draw, match.probs.draw),
            "패": (match.odds.away, match.probs.away)}
    for label, (odd, prob) in want.items():
        got = rows.get(label)
        if got is None:
            out.append(_src(DATA, f"시장 표에 '{label}' 줄이 없음", match.no,
                            "market", "시장 기준선 블록", doc))
            continue
        go, gp = to_number(got[0]), to_number(got[1].rstrip("%"))
        if go is None or abs(float(go) - odd) > 0.005 + 1e-9:
            out.append(_src(DATA, f"배당({label})이 원본 자료와 다름", match.no,
                            "market", "시장 기준선 블록", doc, f"{odd}", got[0]))
        if gp is None or abs(float(gp) - prob * 100) > 0.05 + 1e-9:
            out.append(_src(DATA, f"내재확률({label})이 원본 자료와 다름", match.no,
                            "market", "시장 기준선 블록", doc, f"{prob * 100:.4f}%",
                            got[1]))
    return out


# ==========================================================================
# 파일 찾기
# ==========================================================================
def _git(args: list) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(REPO)] + args, capture_output=True)


def read_web_ref(ref: str, round_id: str) -> bytes | None:
    proc = _git(["show", f"{ref}:reports/toto_{round_id}.html"])
    return proc.stdout if proc.returncode == 0 else None


def ref_rounds(ref: str) -> set:
    proc = _git(["ls-tree", "--name-only", ref, "reports/"])
    if proc.returncode != 0:
        return set()
    names = proc.stdout.decode("utf-8", "replace").split()
    return {m.group(1) for n in names if (m := PUBLISH_NAME.match(Path(n).name))}


def dir_rounds(folder: Path) -> set:
    if not folder.is_dir():
        return set()
    return {m.group(1) for p in folder.iterdir()
            if p.is_file() and (m := PUBLISH_NAME.match(p.name))}


def default_paths() -> tuple[Path, Path]:
    """(원본 reports 폴더, 게시 worktree). 설정·게시 모듈의 규칙을 그대로 쓴다."""
    from toto import pagespublish, settings
    s = settings.load_settings()
    return s.output_dir, pagespublish.default_pages_dir(REPO)


# ==========================================================================
# 보고
# ==========================================================================
def _merge_docs(findings: list) -> list:
    """두 HTML 에서 똑같이 나온 원본 자료 대조 차이를 한 건으로 합친다.

    원본과 웹이 같으면 같은 차이가 두 번 나오는데, 두 번 적으면 건수가
    부풀고 '웹이 따로 틀렸다' 처럼 읽힌다. 어느 문서에서 나왔는지는 남긴다.
    """
    merged: dict = {}
    for f in findings:
        key = (f.kind, f.what, f.match, f.cat, f.where, f.original, f.web)
        if key in merged:
            if f.doc and f.doc not in merged[key].doc:
                merged[key].doc += f" · {f.doc}"
        else:
            merged[key] = Finding(f.kind, f.what, f.match, f.cat, f.where,
                                  f.original, f.web, f.doc, f.labels)
    return list(merged.values())


def _print_findings(L, findings: list, limit: int) -> None:
    for f in findings[:limit]:
        L("")
        L(f"경기: {f.match if f.match is not None else '-'}")
        L(f"항목: {CAT_KO.get(f.cat, f.cat)} — {f.what}")
        where = " · ".join(x for x in (f.doc, f.where) if x)
        if where:
            L(f"위치: {where}")
        L(f"{f.labels[0]}: {f.original}")
        L(f"{f.labels[1]}: {f.web}")
        L(f"분류: {KIND_KO[f.kind]}")
    if len(findings) > limit:
        L(f"\n… 외 {len(findings) - limit}건 (--limit 으로 늘릴 수 있다)")


def run(args) -> int:
    reports_dir = pages_dir = None
    if args.original is None or (args.web is None and args.web_ref is None):
        reports_dir, pages_dir = default_paths()
    if args.pages_dir is not None:
        pages_dir = args.pages_dir

    round_id = args.round
    if round_id is None:
        if args.original is not None and (m := PUBLISH_NAME.match(args.original.name)):
            round_id = m.group(1)
        else:
            orig = dir_rounds(reports_dir) if reports_dir else set()
            web = (ref_rounds(args.web_ref) if args.web_ref
                   else dir_rounds(pages_dir / "reports") if pages_dir else set())
            both = orig & web
            if not both:
                print("검증할 회차를 찾지 못했습니다 — 원본과 웹 양쪽에 있는 "
                      "toto_<회차>.html 이 없습니다.")
                print(f"  원본: {sorted(orig) or '없음'} ({reports_dir})")
                print(f"  웹  : {sorted(web) or '없음'} "
                      f"({args.web_ref or pages_dir})")
                return 2
            round_id = max(both, key=int)
    if not re.fullmatch(r"\d+", str(round_id)):
        print(f"회차는 숫자여야 합니다: {round_id!r}")
        return 2

    o_path = args.original or reports_dir / f"toto_{round_id}.html"
    if args.web is not None:
        w_label, w_raw = str(args.web), (args.web.read_bytes()
                                         if args.web.is_file() else None)
    elif args.web_ref:
        w_label = f"{args.web_ref}:reports/toto_{round_id}.html"
        w_raw = read_web_ref(args.web_ref, round_id)
    else:
        wp = pages_dir / "reports" / f"toto_{round_id}.html"
        w_label, w_raw = str(wp), (wp.read_bytes() if wp.is_file() else None)
    if not Path(o_path).is_file():
        print(f"PC 원본이 없습니다: {o_path}")
        return 2
    if w_raw is None:
        print(f"웹 리포트가 없습니다: {w_label}")
        if not args.web_ref and args.web is None:
            print("  이미 push 했다면 --web-ref origin/gh-pages 로 push 된 판을 볼 수 "
                  "있습니다.")
        return 2
    o_raw = Path(o_path).read_bytes()

    fs = file_stage(o_raw, w_raw)
    do, dw = load_doc("PC 원본", o_raw), load_doc("웹 리포트", w_raw)
    content = compare_docs(do, dw)
    browser = ({"status": "SKIP", "reason": "--no-browser"} if args.no_browser
               else browser_stage(o_raw, w_raw))
    source = ({"status": "SKIP", "reason": "--no-source"} if args.no_source
              else source_stage(round_id, [do, dw]))

    # 원본 ↔ 웹 비교와 원본 자료 ↔ HTML 대조는 **묻는 것이 다르다.** 앞의 것은
    # 웹이 원본을 훼손했나, 뒤의 것은 두 HTML 이 저장된 자료를 그대로 담았나다.
    # 한 줄에 섞으면 원본과 웹이 같은데도 '웹이 다르다' 로 읽힌다.
    findings = list(content["findings"]) + list(browser.get("findings", []))
    if not fs["identical"] and fs["same_after_newline"]:
        findings.append(Finding(DEPLOY, "줄바꿈(CRLF↔LF)·BOM 만 다름", cat="page",
                                where="파일 전체",
                                original=f"CRLF {fs['crlf'][0]}",
                                web=f"CRLF {fs['crlf'][1]}"))
    blocking = [f for f in findings if f.kind in BLOCKING]
    for f in browser.get("findings", []):
        if f.kind in BLOCKING and f.cat in content["cat_status"]:
            content["cat_status"][f.cat] = "FAIL"
    source_blocking = _merge_docs([f for f in source.get("findings", [])
                                   if f.kind in BLOCKING])
    verdict = "FAIL" if blocking or source_blocking else "PASS"

    L = print
    bar = "=" * 50
    L(bar)
    L("PC 원본 리포트 ↔ 웹 리포트 일치 검증")
    L(bar)
    L("")
    L(f"회차: {round_id}")
    L("")
    L("[파일]")
    L(f"PC 원본: {o_path}")
    L(f"  크기: {fs['size'][0]:,} bytes · SHA256: {fs['sha'][0]}")
    L(f"웹 리포트: {w_label}")
    L(f"  크기: {fs['size'][1]:,} bytes · SHA256: {fs['sha'][1]}")
    L("")
    L("[파일 비교]")
    if fs["identical"]:
        L("SHA256: 일치 (바이트까지 같다)")
    else:
        L("SHA256: 다름")
        L(f"줄바꿈·BOM 을 걷은 뒤: {'일치' if fs['same_after_newline'] else '다름'}"
          f" (CRLF 원본 {fs['crlf'][0]} · 웹 {fs['crlf'][1]}"
          f" · BOM 원본 {fs['bom'][0]} · 웹 {fs['bom'][1]})")
        if not fs["same_after_newline"]:
            L(f"바뀐 줄 수(정규화 후): {fs['lines_changed']}")
    L(f"파일 크기: {'일치' if fs['size'][0] == fs['size'][1] else '다름'}"
      f" ({fs['size'][0] - fs['size'][1]:+,} bytes)")
    L("")
    L("[핵심 데이터 비교] PC 원본 ↔ 웹 리포트")
    for key, ko in CATEGORIES:
        L(f"{ko}: {content['cat_status'][key]}")
    L(f"숫자 표기만 다른 곳: {content['fmt_only']}개 (값은 같다)")
    L(f"내장 JSON: 원본 {len(do.json_blobs)}개 · 웹 {len(dw.json_blobs)}개")
    L("")
    L(f"[브라우저 표시 비교] {browser['status']}"
      + (f" — {browser['reason']}" if browser.get("reason") else ""))
    for width, inf in browser.get("info", {}).items():
        L(f"  {width}px: 경기 카드 원본 {inf['cards'][0]} · 웹 {inf['cards'][1]}"
          f" · 가로 넘침 원본 {inf['overflow'][0]} · 웹 {inf['overflow'][1]}")
    source_status = source["status"]
    if source_status != "SKIP":
        source_status = "FAIL" if source_blocking else "PASS"
    L(f"[원본 자료 대조] {source_status}"
      + (f" — {source['reason']}" if source.get("reason") else "")
      + (f" ({' · '.join(source['checked'])})" if source.get("checked") else ""))
    L("")
    L("[경기별 결과]")
    L("")
    numbers = sorted(set(do.match_order) | set(dw.match_order)
                     | set(do.overview_order))
    for no in numbers:
        web_bad = [f for f in blocking if f.match == no]
        src_bad = [f for f in source_blocking if f.match == no]
        parts = ([f"웹 {len(web_bad)}건"] if web_bad else []) \
            + ([f"원본 자료 {len(src_bad)}건"] if src_bad else [])
        L(f"{no}경기: " + (f"FAIL ({' · '.join(parts)})" if parts else "PASS"))
    L("")
    L("[차이] PC 원본 ↔ 웹 리포트")
    if not blocking:
        L("없음")
    _print_findings(L, blocking, args.limit)
    if source_blocking:
        L("")
        L("[차이] 원본 자료(Panel Result·회차 저장본) ↔ HTML")
        _print_findings(L, source_blocking, args.limit)
    soft = [f for f in findings if f.kind not in BLOCKING]
    if soft:
        L("")
        L("[표현·배포 차이 — 내용 불일치 아님]")
        for f in soft[: args.limit]:
            loc = f" · {f.match}경기" if f.match is not None else ""
            extra = f" ({f.original} → {f.web})" if f.original or f.web else ""
            L(f"- {KIND_KO[f.kind]}{loc}: {f.what}"
              + (f" · {f.where}" if f.where else "") + extra)
    L("")
    L(bar)
    L(f"최종 결과: {verdict}")
    L(bar)
    if blocking:
        L("")
        L("판단: 웹 리포트가 PC 원본과 일치하지 않음 — push 하지 마십시오.")
    elif source_blocking:
        L("")
        L("판단: 웹 리포트는 PC 원본과 같지만, HTML 이 원본 자료와 다릅니다 — "
          "리포트를 다시 만든 뒤 게시하십시오.")
    return 0 if verdict == "PASS" else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="PC 원본 리포트와 웹(GitHub Pages) 리포트의 내용 일치를 검증한다.")
    p.add_argument("round", nargs="?", help="회차 (생략하면 양쪽에 다 있는 최근 회차)")
    p.add_argument("--original", type=Path, help="PC 원본 HTML 경로")
    p.add_argument("--web", type=Path, help="웹 리포트 HTML 경로")
    p.add_argument("--web-ref", help="push 된 판을 git 에서 읽는다 (예: origin/gh-pages)")
    p.add_argument("--pages-dir", type=Path, help="gh-pages worktree 경로")
    p.add_argument("--no-browser", action="store_true", help="브라우저 비교(C) 생략")
    p.add_argument("--no-source", action="store_true", help="원본 자료 대조(S) 생략")
    p.add_argument("--limit", type=int, default=40, help="보여줄 차이 개수")
    return p


def main(argv=None) -> int:
    try:
        from toto.cli import safe_console
        safe_console()
    except Exception:                                        # noqa: BLE001
        pass
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
