# 详细更新日志

> 这里按提交逐条记录项目发生过的每一次改动，用来查"某个小改动是哪次做的"。
> **面向"这一版有什么变化"的摘要见 [重要变更](CHANGELOG.md)**，面向当前能力见 [文档总入口](README.md)。
>
> 骨架由 `python scripts/build_changelog_detail.py` 从 `git log` 生成，**不要手工调整提交行**；
> 需要补充原因、影响或验证结果时，在对应提交下方缩进两格写 `  - 说明：…`，重新生成会按短哈希保留。
> 本文件只包含**已提交**的历史，工作区未提交的改动不会出现在这里。

共 66 条提交，覆盖 2026-08-17 至 2026-09-14。

## 2026-09-14

- `77a0e80` **文档** split reader-facing and developer docs, consolidate to 11 files
- `9039c77` **新增** refresh wiki data and calibrate generation threshold
- `5acd835` **文档** expand README with feature walkthrough and real UI screenshots
- `3de2389` **文档** record logo provenance and untrack unused mascot art
- `f24f38e` **文档** record asset and data provenance with a full disclaimer
- `c2760e8` **新增** add query backdrop and portrait carousel

## 2026-09-13

- `a63d7bc` **新增** polish archive visuals and biological helix motion

## 2026-09-12

- `b634b21` **杂项** refresh versioned eval baseline after implementation changes
- `c0c0f7e` **新增** rebuild web as spatial archive with double helix

## 2026-09-09

- `f4ad925` **新增** align mini program with web visual system
- `22c5973` **新增** rebuild web interface with official Endfield artwork and motion
- `eb7bd32` **新增** adopt Endfield motion language

## 2026-09-08

- `520a7f6` **修复** bound LLM retries with a total deadline
- `72de909` **性能** improve retrieval evidence and evaluation provenance
- `8394752` **修复** harden backend retrieval and indexing

## 2026-09-03

- `4a4ec99` **修复** prevent truncated and misrouted RAG answers
- `d4546b3` **新增** stream RAG answers and prewarm indexes

## 2026-08-29

- `3446349` **修复** make eval manifest reproducible in CI
- `afcb9db` **新增** add trace-driven RAG quality loop
- `ab085c1` **修复** harden API access and media proxy safety
- `30c8f54` **杂项** upgrade Vite toolchain to patched 6.4 release

## 2026-08-28

- `767243e` **修复** honor retrieval plans and restore frontend query interactions
- `02a720d` **文档** record web UI experience optimizations and miniprogram markdown rendering
- `335040a` **新增** render markdown in miniprogram ask answers
- `51a611b` **新增** enlarge skill dynamic images with side-by-side text layout
- `3aff8d2` **修复** proxy tree node covers, compact X spacing, auto-fit tree to container
- `01ed701` **新增** render markdown in ask answers, fallback cover images
- `2f65703` **修复** tree layout unit/px explosion, lock scroll during entry, cover fallback, logo clip
- `348ff6e` **修复** inset content from clip-path corners so edge text is fully visible
- `ffa3471` **修复** keep content layer above mascot stickers (z-index 9 vs 8)
- `0d06a7b` **修复** animate progress fill inline and restore mascot clearance paddings
- `b597c30` **修复** restore reveal-on-scroll observer and scroll parallax
- `42d1aeb` **修复** serve /assets from web/assets in dev and copy to dist on build; fix SVG clip id
- `b670a14` **新增** rebuild frontend with React/TS/Vite and framer-motion
- `2a50841` **文档** add agent workflow design document
- `90d52ab` **新增** upgrade RAG with semantic planner, operator audio and index versioning

## 2026-08-26

- `53c1b2b` **文档** add friend server deployment handoff guide
- `1b9f661` **新增** harden API and add self-hosted deployment

## 2026-08-21

- `f77cda5` **新增** add miniprogram and production deployment setup

## 2026-08-20

- `4c2dfbc` **文档** add project README
- `fcdb413` **重构** streamline docs and clarify core workflows
- `8e68fc6` **新增** redesign mechanical entry sequence
- `9bf923f` **文档** unify RAG and knowledge graph architecture
- `53ff4fe` **修复** focus generation context across full documents
- `a29a62b` **修复** answer compound kinship questions
- `6f5ba5b` **修复** cache answers and expand operator media
- `9d80fb5` **新增** expand GraphRAG relationship coverage
- `26eaf9c` **新增** add auditable incremental GraphRAG

## 2026-08-19

- `9351461` **修复** contain wide tables in independent scrollers
- `8559580` **新增** add draggable scroll tracks to all tables
- `c3157c5` **修复** restore operator media and widen dossier UI
- `2e29721` **新增** add interactive operator dossiers
- `dd693f3` **新增** add RAG observability and quality gates
- `2978b17` **文档** audit RAG architecture monitoring and evaluation

## 2026-08-18

- `e311ab5` **文档** credit character artwork
- `a72d754` **新增** add local type and animated character art
- `53aaf6a` **新增** add dimensional polygon visual system
- `d841a78` **新增** enrich interface shapes and motion

## 2026-08-17

- `0122083` **文档** record LLM runtime recovery
- `168d45c` **新增** add vertical image recipe tree
- `e943a8e` **新增** redesign frontend as industrial archive
- `d9c1e9b` **构建** add reproducible Railway deployment
- `5230c62` **修复** restore missing RAG entries and improve recall
- `d2caa6c` **新增** improve synthesis tree interactions
- `5361025` **测试** cover synthesis API invariants
- `651c05b` **杂项** establish project baseline
