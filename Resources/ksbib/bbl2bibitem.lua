#!/usr/bin/env texlua
-- bbl2bibitem.lua  (proof of concept)
--
-- biblatex+biber 로 조판된 서지 목록을 투고용 thebibliography 환경으로 뽑아준다.
--
--   texlua bbl2bibitem.lua main.tex [-o out.tex] [--style numeric|authoryear|auto]
--
-- 동작 원리
--   1. main.tex 를 "그대로" LuaLaTeX 로 한 번 더 컴파일한다(PDF 는 버린다).
--      이때 biblatex 의 bibliography 환경만 가로채서, 각 항목이 문단으로
--      조판되기 직전(pre_linebreak_filter)에 노드 리스트를 읽어 TeX 소스로 되돌린다.
--      => 사용자가 쓰는 스타일/lbx/자작 sty 가 만든 서식이 그대로 나온다.
--   2. main.bbl 은 복사해서 쓰므로 biber 를 다시 돌리지 않는다.
--
-- 이 파일은 두 역할을 겸한다.
--   * texlua 로 실행하면 CLI 드라이버
--   * LuaLaTeX 안에서 dofile 되면(BBLH_INSIDE == true) 노드 수확 모듈

if BBLH_INSIDE then
  ---------------------------------------------------------------------------
  -- 모듈 모드 (LuaTeX 내부)
  ---------------------------------------------------------------------------
  BBLH = BBLH or {}
  local M = BBLH
  local opts = BBLH_OPTS or {}

  local on, curkey, curlabel = false, nil, nil
  local entries, order = {}, {}      -- entries[key] = text
  local labels = {}                  -- labels[key] = {a=..., y=...}
  local warnings = {}

  local GLYPH = node.id("glyph")
  local GLUE  = node.id("glue")
  local HLIST = node.id("hlist")
  local VLIST = node.id("vlist")
  local DISC  = node.id("disc")
  local MATH  = node.id("math")

  local function warn(msg)
    warnings[#warnings + 1] = msg
  end

  -- 글꼴 이름에서 서체 속성을 추정 -------------------------------------
  local fcache = {}
  local function fontstyle(id)
    local s = fcache[id]
    if s then return s end
    local f = font.getfont(id) or {}
    local name = table.concat({
      f.fullname or "", f.psname or "", f.fontname or "", f.name or "",
      (f.filename or ""):match("[^/\\]*$") or "",
    }, " "):lower()
    s = {
      i = (name:find("italic") or name:find("oblique") or name:find("slanted")) and true or false,
      b = (name:find("bold") or name:find("heavy") or name:find("black")) and true or false,
      c = (name:find("caps") or name:find("smallcap")) and true or false,
      m = (name:find("mono") or name:find("typewriter") or name:find("courier")) and true or false,
    }
    s.math = (name:find("math") or name:find("cmmi") or name:find("cmsy") or name:find("cmex")
              or name:find("msam") or name:find("msbm") or name:find("eufm") or name:find("rsfs")) and true or false
    s.key = (s.i and "i" or "") .. (s.b and "b" or "") .. (s.c and "c" or "") .. (s.m and "m" or "")
    fcache[id] = s
    return s
  end

  -- 글리프 슬롯 -> 원래 유니코드 목록 (luaotfload 의 tounicode: UTF-16BE 16진 문자열)
  local function tounicode(fid, c)
    local f = font.getfont(fid)
    local ch = f and f.characters and f.characters[c]
    local t = ch and ch.tounicode
    if type(t) ~= "string" or t == "" then return nil end
    local cps, i = {}, 1
    while i + 3 <= #t do
      local u = tonumber(t:sub(i, i + 3), 16)
      i = i + 4
      if not u then return nil end
      if u >= 0xD800 and u <= 0xDBFF and i + 3 <= #t then
        local lo = tonumber(t:sub(i, i + 3), 16)
        if lo and lo >= 0xDC00 and lo <= 0xDFFF then
          u = 0x10000 + (u - 0xD800) * 0x400 + (lo - 0xDC00)
          i = i + 4
        end
      end
      cps[#cps + 1] = u
    end
    return cps
  end

  -- 노드 리스트 -> {ch=, st=, sp=} 목록 -----------------------------------
  local function collect(head, out)
    for n in node.traverse(head) do
      local id = n.id
      if id == GLYPH then
        if n.components then
          -- 합자: 원래 글자들로 풀어 쓴다
          collect(n.components, out)
        else
          local c = n.char
          local fs = fontstyle(n.font)
          if fs.math then
            -- 수학 글꼴 글리프는 TeX 소스로 복원할 수 없다.
            -- 수식($…$) 안이면 수식 전체를 닫는 지점에서 표지 하나로 바꾼다(아래 MATH 노드).
            -- 수식 노드 밖이면 연속 구간마다 표지 하나.
            out.hasmath = true
            if (out.mdepth or 0) > 0 then
              out.mhas = true
            elseif not out.inmathfont then
              out.inmathfont = true
              out[#out + 1] = { raw = "[[MATH?]]" }
            end
          elseif c == 0xF0000 then
            -- luatexko 가 한글 음절 뒤에 넣는 보이지 않는 표지 글리프(U+F0000): 본문이 아니다
          elseif c and c > 0 then
            out.inmathfont = false
            local st = fs.key
            if c >= 0xE000 and c <= 0xF8FF then
              -- OpenType 기능(smcp, onum, swsh ...)이 치환한 글리프: luaotfload 가 PDF 복사용으로
              -- 보관한 원래 유니코드(tounicode)로 되돌린다.
              local cps = tounicode(n.font, c)
              if cps and #cps > 0 then
                -- 치환 글리프의 원문이 글자이면 스몰캡 등 글자 변형으로 보고 \textsc 를 건다
                if #cps == 1 and cps[1] < 0x250 and utf8.char(cps[1]):match("%a") and not st:find("c") then
                  st = st .. "c"
                end
                for _, u in ipairs(cps) do out[#out + 1] = { c = u, st = st } end
              else
                out[#out + 1] = { c = c, st = st }
              end
            else
              out[#out + 1] = { c = c, st = st }
            end
          end
        end
      elseif id == GLUE then
        -- 단어 사이 공백만 남긴다 (0폭 글루, 좌우 skip 등은 버린다)
        -- spaceskip(13)/xspaceskip(14) 가 일반 단어 간격이다.
        -- luatexko 가 한글-라틴/문장부호 사이에 넣는 미세 글루(subtype 0, 폭 < 2pt)는 버린다.
        -- \space, \  등으로 직접 넣은 글루(subtype 0)는 폭 2pt 이상 + 늘어남이 있을 때만 공백으로 본다.
        local w = n.width or 0
        local sub = n.subtype
        if sub == 13 or sub == 14 or (sub == 0 and w >= 131072 and (n.stretch or 0) > 0) then
          out[#out + 1] = { sp = true }
        end
      elseif id == HLIST or id == VLIST then
        if n.subtype ~= 3 then -- 3 = parindent 상자
          if n.list then collect(n.list, out) end
        end
      elseif id == DISC then
        if n.replace then collect(n.replace, out) end
      elseif id == MATH then
        -- (url 패키지도 수식 모드를 쓰므로 수식 노드만으로는 수식이라 할 수 없다:
        --  on..off 사이에 수학 글꼴 글리프가 하나라도 있을 때만 수식 한 덩어리로 본다)
        if n.subtype == 0 then
          if (out.mdepth or 0) == 0 then out.mstart = #out + 1; out.mhas = false end
          out.mdepth = (out.mdepth or 0) + 1
        elseif (out.mdepth or 0) > 0 then
          out.mdepth = out.mdepth - 1
          if out.mdepth == 0 then
            if out.mhas then
              for k = #out, out.mstart, -1 do out[k] = nil end
              out[#out + 1] = { raw = "[[MATH?]]" }
              out.inmathfont = true
            end
            out.mhas = false
          end
        end
      end
    end
    return out
  end

  -- TeX 소스로 되돌리기 -------------------------------------------------
  local map = {
    [0x00A0] = "~",
    [0x2010] = "-", [0x2011] = "-", [0x2012] = "--", [0x2013] = "--", [0x2014] = "---",
    [0x2018] = "`", [0x2019] = "'", [0x201C] = "``", [0x201D] = "''",
    [0xFB00] = "ff", [0xFB01] = "fi", [0xFB02] = "fl", [0xFB03] = "ffi", [0xFB04] = "ffl",
    [0x2009] = "\\,", [0x202F] = "\\,",
  }
  local esc = {
    ["\\"] = "\\textbackslash{}", ["{"] = "\\{", ["}"] = "\\}",
    ["&"] = "\\&", ["%"] = "\\%", ["$"] = "\\$", ["#"] = "\\#", ["_"] = "\\_",
    ["~"] = "\\textasciitilde{}", ["^"] = "\\textasciicircum{}",
  }
  local function escchar(c)
    if opts.keepunicode == nil and map[c] then return map[c] end
    if c >= 0xE000 and c <= 0xF8FF then
      warn(string.format("알 수 없는 글리프 U+%04X", c))
      return "?"
    end
    local ch = utf8.char(c)
    return esc[ch] or ch
  end

  local function wrap(style, s)
    if style:find("m") then s = "\\texttt{" .. s .. "}" end
    if style:find("c") then s = "\\textsc{" .. s .. "}" end
    if style:find("b") then s = "\\textbf{" .. s .. "}" end
    if style:find("i") then s = "\\emph{" .. s .. "}" end
    return s
  end

  local function render(list)
    -- 앞뒤 공백 제거, 연속 공백 병합
    local items = {}
    for _, it in ipairs(list) do
      if it.sp then
        if #items > 0 and not items[#items].sp then items[#items + 1] = { sp = true } end
      elseif it.raw then
        for _, cp in utf8.codes(it.raw) do items[#items + 1] = { c = cp, st = "", raw = true } end
      else
        items[#items + 1] = it
      end
    end
    while #items > 0 and items[#items].sp do items[#items] = nil end

    -- 공백의 서체: 앞뒤 글자가 같은 서체일 때만 그 서체를 따른다
    for i, it in ipairs(items) do
      if it.sp then
        local p, q = items[i - 1], items[i + 1]
        while p and p.sp do p = items[i - 1] end
        it.st = (p and q and not q.sp and p.st == q.st) and p.st or ""
      end
    end

    -- URL 탐지 (일반 글자열 위에서)
    local plain, idx = {}, {}
    for i, it in ipairs(items) do
      plain[#plain + 1] = it.sp and " " or utf8.char(it.c)
      idx[#idx + 1] = i
    end
    local ptxt = table.concat(plain)
    -- 글자 단위 인덱스 -> items 인덱스 (모두 1:1, utf8.char 가 1글자이므로 문자 수 기준)
    local chars = {}
    for _, cp in utf8.codes(ptxt) do chars[#chars + 1] = cp end
    local urlfrom = {}
    do
      local pos = 1
      while true do
        local s, e = ptxt:find("https?://%S+", pos)
        if not s then break end
        -- 바이트 위치 -> 문자 위치
        local cs = utf8.len(ptxt, 1, s - 1) or 0
        local ce = utf8.len(ptxt, 1, e)
        -- 끝의 구두점은 URL 에서 제외
        while ce > cs + 1 do
          local ch = utf8.char(chars[ce])
          if ch:match("[%.,;:%)%]]") then ce = ce - 1 else break end
        end
        urlfrom[cs + 1] = ce
        pos = e + 1
      end
    end

    local out, i, n = {}, 1, #items
    while i <= n do
      if urlfrom[i] then
        local e = urlfrom[i]
        local raw = {}
        for k = i, e do raw[#raw + 1] = utf8.char(items[k].c) end
        out[#out + 1] = "\\url{" .. table.concat(raw) .. "}"
        i = e + 1
      else
        local st = items[i].st or ""
        local buf = {}
        local k = i
        while k <= n and not urlfrom[k] and (items[k].st or "") == st do
          buf[#buf + 1] = items[k].sp and " " or escchar(items[k].c)
          k = k + 1
        end
        local text = table.concat(buf)
        out[#out + 1] = (st == "") and text or wrap(st, text)
        i = k
      end
    end
    local res = table.concat(out)
    -- \TeX 로고는 글리프 TEX (E 가 내려앉은 모양)로 나온다 → 되돌린다
    res = res:gsub("%f[%u]TEX%f[^%u]", "\\TeX{}")
    if list.hasmath then
      -- 바이트로 자르면 한글이 반쪽이 되어 잘못된 UTF-8 이 나온다: 글자 단위로 자른다
    local cut = utf8.offset(res, 31)
    warn("수식이 포함된 항목이 있습니다 (수식은 복원되지 않음): " .. (cut and res:sub(1, cut - 1) or res))
    end
    return res
  end

  -- 문단 훅 ---------------------------------------------------------------
  local function filter(head)
    -- 출력 루틴 안에서 조판되는 문단(쪽 번호, 머리말/꼬리말)은 항목이 아니다.
    -- 항목 사이에서 쪽이 넘어가면 쪽 번호 문단이 키를 가로채 "1" 같은 항목이 만들어진다.
    if status and status.output_active then return true end
    if on and (curkey or curlabel) then
      local list = collect(head, {})
      local txt = render(list)
      if txt ~= "" then
        if curlabel then
          local k, which = curlabel[1], curlabel[2]
          labels[k] = labels[k] or {}
          labels[k][which] = txt
        else
          if not entries[curkey] then order[#order + 1] = curkey end
          entries[curkey] = txt
        end
        curkey, curlabel = nil, nil
      end
      -- 내용이 빈 문단(\endgraf 가 만든 빈 단락 등)은 키를 소모하지 않는다:
      -- 키를 지워 버리면 뒤따르는 진짜 항목이 키 없이 처리되어 빠진다
    end
    return true
  end

  function M.install()
    luatexbase.add_to_callback("pre_linebreak_filter", filter, "bbl2bibitem.harvest")
    luatexbase.add_to_callback("stop_run", M.write, "bbl2bibitem.write")
  end
  function M.setstyle(st) if opts.style == "auto" or opts.style == nil then opts.style = st end end
  function M.begin()  on = true  end
  function M.finish() on = false; curkey = nil end
  function M.key(k)   curkey = k; curlabel = nil end

  -- author-year 용 라벨 수확: 문서 끝에서 \citeauthor / \citeyear 를 돌린다
  function M.labelrun()
    if opts.style ~= "authoryear" then return end
    on = true
    for _, k in ipairs(order) do
      tex.print(string.format("\\par\\directlua{BBLH.lab('%s','a')}\\citeauthor{%s}", k, k))
      tex.print(string.format("\\par\\directlua{BBLH.lab('%s','y')}\\citeyear{%s}", k, k))
    end
    tex.print("\\par\\directlua{BBLH.finish()}")
  end
  function M.lab(k, which) curlabel = { k, which }; curkey = nil end

  local function wrapped(s, width)
    local lines, cur = {}, ""
    for word in s:gmatch("%S+") do
      if cur == "" then cur = word
      elseif utf8.len(cur .. " " .. word) <= width then cur = cur .. " " .. word
      else lines[#lines + 1] = cur; cur = word end
    end
    if cur ~= "" then lines[#lines + 1] = cur end
    return table.concat(lines, "\n  ")
  end

  function M.write()
    local f = assert(io.open(opts.outfile, "wb"))
    local n = #order
    local w = (n < 10) and "9" or (n < 100) and "99" or "999"
    f:write("\\begin{thebibliography}{", w, "}\n")
    for _, k in ipairs(order) do
      local lab = ""
      if opts.style == "authoryear" then
        local l = labels[k] or {}
        if l.a and l.y then lab = "[" .. l.a .. "(" .. l.y .. ")]" end
      end
      f:write("\\bibitem", lab, "{", k, "}\n  ", wrapped(entries[k], 76), "\n")
    end
    f:write("\\end{thebibliography}\n")
    f:close()
    local g = io.open(opts.outfile .. ".warnings", "wb")
    for _, m in ipairs(warnings) do g:write(m, "\n") end
    g:close()
  end

  return M
end

---------------------------------------------------------------------------
-- CLI 드라이버 (texlua)
---------------------------------------------------------------------------
local lfs = require("lfs")

local function usage()
  io.stderr:write([[
사용법: texlua bbl2bibitem.lua main.tex [옵션]
  -o FILE            출력 파일 (기본: main-thebib.tex, '-' 이면 표준출력)
  --style STYLE      numeric | authoryear | auto (기본 auto: .bbl 에 labelnumber 가 있으면 numeric)
  --engine NAME      수확용 컴파일러 (기본 lualatex)
  --keep             임시 디렉터리를 지우지 않음 (디버깅)
  --single           \printbibliography 를 하나로 합쳐 수확 (en+ko 에서 항목이 빠질 때)
]])
  os.exit(1)
end

local args = { }
local i = 1
local texfile, outfile, style, engine, keep, forcesingle = nil, nil, "auto", "lualatex", false, false
while arg[i] do
  local a = arg[i]
  if a == "-o" then i = i + 1; outfile = arg[i]
  elseif a == "--style" then i = i + 1; style = arg[i]
  elseif a == "--engine" then i = i + 1; engine = arg[i]
  elseif a == "--keep" then keep = true
  elseif a == "--single" then forcesingle = true
  elseif a == "-h" or a == "--help" then usage()
  elseif not texfile then texfile = a
  else usage() end
  i = i + 1
end
if not texfile then usage() end

local function exists(p) return lfs.attributes(p, "mode") ~= nil end
if not exists(texfile) and exists(texfile .. ".tex") then texfile = texfile .. ".tex" end
if not exists(texfile) then io.stderr:write("파일이 없습니다: " .. texfile .. "\n"); os.exit(1) end

local script = arg[0]
if not script:match("^/") and not script:match("^%a:[/\\]") then
  script = lfs.currentdir() .. "/" .. script
end
script = script:gsub("\\", "/")

local dir = texfile:match("^(.*)[/\\][^/\\]*$") or "."
local file = texfile:match("([^/\\]*)$")
local base = file:gsub("%.tex$", "")
lfs.chdir(dir)

local bbl = base .. ".bbl"
if not exists(bbl) then
  io.stderr:write(bbl .. " 이(가) 없습니다. 먼저 lualatex → biber → lualatex 를 실행하세요.\n")
  os.exit(1)
end
local bf = io.open(bbl, "rb"); local bbltext = bf:read("*a"); bf:close()

local function q(s) return (s:gsub("\\", "/")) end
if outfile == nil then outfile = base .. "-thebib.tex" end

-- 수확 한 번: single=true 이면 사용자의 \printbibliography 들을 하나로 합쳐 모든 항목을 한 번에 찍는다
local runno = 0
local function harvest(single)
  runno = runno + 1
  local jobname = base .. "-bibharvest"
  local tmp = (os.getenv("TMPDIR") or os.getenv("TEMP") or "/tmp"):gsub("\\", "/") .. "/" .. jobname .. "-" .. os.time() .. "-" .. runno
  assert(lfs.mkdir(tmp))
  local rawout = tmp .. "/" .. jobname .. ".out"
  local wf = assert(io.open(tmp .. "/" .. jobname .. ".bbl", "wb")); wf:write(bbltext); wf:close()
  local merge = single and [[
  \let\bblorigpb\printbibliography
  \newtoggle{bblprinted}
  \renewrobustcmd*{\printbibliography}[1][]{\iftoggle{bblprinted}{}{\toggletrue{bblprinted}\bblorigpb[heading=none]}}
  \renewrobustcmd*{\printbibheading}[1][]{}
]] or ""
  local wrapper = string.format([[
\RequirePackage{etoolbox}
\directlua{BBLH_INSIDE=true BBLH_OPTS={style="%s",outfile="%s"} dofile("%s")}
\AtEndPreamble{%%
  \directlua{BBLH.install()}%%
  \defbibenvironment{bibliography}
    {\directlua{BBLH.begin()}}
    {\endgraf\directlua{BBLH.finish()}}
    {\endgraf\directlua{BBLH.key("\thefield{entrykey}")}}%%
%s  \AtEndDocument{%%
    \iftoggle{blx@labelnumber}{\directlua{BBLH.setstyle("numeric")}}{\directlua{BBLH.setstyle("authoryear")}}%%
    \directlua{BBLH.labelrun()}}%%
}
\input{%s}
]], style, q(rawout), q(script), merge, q(file))
  local wr = assert(io.open(tmp .. "/" .. jobname .. ".tex", "wb")); wr:write(wrapper); wr:close()
  local cmd = string.format('%s -interaction=batchmode -halt-on-error -output-directory="%s" "%s/%s.tex" > "%s/run.out" 2>&1',
    engine, tmp, tmp, jobname, tmp)
  os.execute(cmd)
  local result = io.open(rawout, "rb")
  local text, warns = nil, ""
  if result then
    text = result:read("*a"); result:close()
    local wl = io.open(rawout .. ".warnings", "rb")
    if wl then warns = wl:read("*a"); wl:close() end
  else
    io.stderr:write("수확 실패. 로그: " .. tmp .. "/" .. jobname .. ".log\n")
  end
  if keep then io.stderr:write("임시 디렉터리: " .. tmp .. "\n")
  else
    for f in lfs.dir(tmp) do if f ~= "." and f ~= ".." then os.remove(tmp .. "/" .. f) end end
    lfs.rmdir(tmp)
  end
  return text, warns
end

local text, warns = harvest(forcesingle)
if not text then os.exit(2) end

-- .bbl 의 항목과 대조: 빠진 것이 있으면 한 목록 방식으로 다시 수확해 보충한다
-- (en+ko 처럼 \printbibliography 를 여러 번 부르는 문서에서 항목이 빠지는 경우가 보고됨)
local function bibkeys(t, pat) local ks, seen = {}, {} for k in t:gmatch(pat) do if not seen[k] then seen[k] = true; ks[#ks + 1] = k end end return ks, seen end
local _, have = bibkeys(text, "\\bibitem%b[]{([^}]+)}")
local _, have2 = bibkeys(text, "\\bibitem{([^}]+)}")
for k in pairs(have2) do have[k] = true end
local want = bibkeys(bbltext, "\\entry{([^}]+)}{")
local lost = {}
for _, k in ipairs(want) do if not have[k] then lost[#lost + 1] = k end end
if #lost > 0 and not forcesingle then
  io.stderr:write("경고: 첫 수확에서 빠진 항목: " .. table.concat(lost, ", ") .. " → 한 목록 방식으로 재수확합니다.\n")
  local t2 = harvest(true)
  if t2 then
    local add = {}
    for _, k in ipairs(lost) do
      local item = t2:match("(\\bibitem[^\n]*{" .. k:gsub("%p", "%%%0") .. "}.-)\n\\bibitem") or t2:match("(\\bibitem[^\n]*{" .. k:gsub("%p", "%%%0") .. "}.-)\n\\end{thebibliography}")
      if item then add[#add + 1] = item .. "\n" end
    end
    if #add > 0 then
      text = text:gsub("\\end{thebibliography}", function() return table.concat(add) .. "\\end{thebibliography}" end, 1)
      io.stderr:write("보충한 항목: " .. #add .. " (목록 끝에 덧붙였으므로 순서가 PDF 와 다를 수 있습니다)\n")
    end
  end
end

if outfile == "-" then
  io.write(text)
else
  local of = assert(io.open(outfile, "wb")); of:write(text); of:close()
  io.stderr:write(string.format("쓰기 완료: %s (style=%s)\n", outfile, style))
end
if warns ~= "" then io.stderr:write("경고:\n" .. warns) end

