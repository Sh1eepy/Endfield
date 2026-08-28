// 与后端 scripts/api_server.py / rag_ask.py 返回结构一一对应的类型定义。

// ---------- /api/synthesis ----------

export interface RefItem {
  name: string
  count?: number | null
  showType?: string
}

export interface SynTreeChild {
  name: string
  item_id: string
  depth: number
  cover?: string
  leaf?: boolean
  count?: number
  truncated?: boolean
  recipes?: SynRecipe[]
}

export interface SynRecipe {
  machine: string
  machine_id: string
  duration: number
  cover?: string
  inputs: SynTreeChild[]
  outputs?: { name: string; count: number }[]
}

export interface SynTree {
  name: string
  item_id: string
  depth: number
  kind?: 'device'
  cover?: string
  leaf?: boolean
  truncated?: boolean
  recipes?: SynRecipe[]
}

/** /api/synthesis 响应：字段按需存在（后端正是如此），前端按存在性判断。 */
export interface SynthesisData {
  ok: boolean
  item?: string
  tree?: SynTree
  ambiguous?: boolean
  candidates?: string[]
  no_recipe?: boolean
  kb?: KbEntry
  cover?: string
  refs?: RefItem[]
  error?: string
}

export type SynthesisResponse = SynthesisData

// ---------- 知识库条目（sections_struct 结构化块） ----------

export interface InlineText { t: 'text'; x: string; color?: string; b?: boolean; i?: boolean }
export interface InlineEntry { t: 'entry'; x: string; img?: string; c?: number }
export interface InlineLink { t: 'link'; u: string; x: string }
export interface InlineImg { t: 'img'; u: string }
export type Inline = InlineText | InlineEntry | InlineLink | InlineImg

export interface BlockPara { t: 'para'; c: Inline[]; kind?: 'heading3'; align?: 'center' }
export interface BlockImg { t: 'img'; u: string; alt?: string }
export interface BlockTable { t: 'table'; r: Inline[][][] }
export interface BlockHr { t: 'hr' }
export interface BlockVideo { t: 'video'; id: string }
export type StructBlock = BlockPara | BlockImg | BlockTable | BlockHr | BlockVideo

export interface KbEntry {
  name: string
  category?: string
  item_id?: string
  sections?: Record<string, string>
  sections_struct?: Record<string, StructBlock[]>
  full_text?: string
  operator_detail?: OperatorDetail
}

// ---------- 干员详情（build_operator_details.py 产物） ----------

export interface OperatorAudio { url: string; title: string; profile: string }
export interface OperatorTab {
  title: string
  icon?: string
  intro?: { imgUrl?: string; name?: string; type?: string; description?: string }
  blocks?: StructBlock[]
  audios?: OperatorAudio[]
}
export interface OperatorWidget {
  title: string
  type?: string
  facts?: { label: string; value: string }[]
  tabs?: OperatorTab[]
}
export interface OperatorChapter { title: string; widgets: OperatorWidget[] }
export interface OperatorDetail {
  item_id?: string
  name: string
  caption?: string
  illustration?: string
  cover?: string
  chapters: OperatorChapter[]
}

// ---------- /api/ask ----------

export interface AskHit {
  meta: { name: string; category: string; item_id: string; chunk_index?: number }
  text: string
  score: number
  vector_sim?: number
  bm25_score?: number
  _direct?: boolean
  _mention?: boolean
  _keyword?: boolean
  _relationship_evidence?: boolean
}

export interface AskSource { name: string; category: string; score: number }

export interface SemanticPlan {
  question_type: string
  topic: string
  entities: string[]
  keywords: string[]
  search_queries: string[]
  routes: string[]
  needs_graph: boolean
  planner_method: string
}

export interface AskRecipeCard {
  machine: string
  duration: number
  inputs: { name: string; count: number }[]
  outputs: { name: string; count: number }[]
}

/** /api/ask 响应：字段按路由按需存在（recipe/device/enum/graph/rag…），前端按存在性判断。 */
export interface AskData {
  ok: boolean
  intent?: string
  method?: string
  route_used?: string
  route?: string
  item?: string
  device?: string
  recipes?: AskRecipeCard[]
  keyword?: string
  matches?: { device: string; output: string; count: number }[]
  candidates?: string[]
  answer?: string
  rejected?: boolean
  sources?: AskSource[]
  hits?: AskHit[]
  semantic_plan?: SemanticPlan
  graph?: unknown
  graph_attempted?: boolean
  interpretation_policy?: string
  enum?: { label: string; category: string; names: string[] }
  names?: string[]
  count?: number
  error?: string
}

export type AskResult = AskData

// ---------- 其他 ----------

export interface NamesResponse { names: string[]; count: number }
export interface HealthResponse { status: string; service: string }
