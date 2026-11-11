/**
 * 后端领域对象在 App 侧的镜像（只放当前用到的字段）。
 * 字段与 server/src/shedguard_server/api/routes/ 下各路由的序列化保持一致。
 */

export interface Pet {
  id: string;
  name: string;
  species: string | null;
  morph: string | null;
  birth_date: string | null;
  created_at_utc: string;
  updated_at_utc: string;
}

export interface PetListResponse {
  items: Pet[];
}

// ---------- 蜕皮状态（POST /api/v1/pets/{id}/check-photo） ----------

export type ShedState = 'normal' | 'opaque' | 'shedding' | 'unknown';

export interface CheckPhotoResult {
  image_id: string;
  state: ShedState;
  confidence: number | null;
  probabilities: Record<string, number> | null;
  advice: string;
}

// ---------- 蜕皮日志（/api/v1/pets/{id}/shed-records） ----------

export interface ShedRecord {
  id: string;
  pet_id: string;
  started_on: string;
  completed_on: string | null;
  notes: string | null;
  created_at_utc: string;
  updated_at_utc: string;
}

export interface ShedRecordListResponse {
  items: ShedRecord[];
}

export interface ShedRecordInput {
  started_on: string;
  completed_on?: string;
  notes?: string;
}

// ---------- 周期预测（GET /api/v1/pets/{id}/shed-prediction） ----------

export interface ShedPrediction {
  predictable: boolean;
  reason: string;
  median_interval_days: number | null;
  mad_days: number | null;
  next_window_start: string | null;
  next_window_end: string | null;
  based_on_cycles: number;
}

// ---------- 知识库（/api/v1/knowledge/topics） ----------

export interface KnowledgeTopicSummary {
  slug: string;
  title: string;
  summary: string;
}

export interface KnowledgeTopicListResponse {
  items: KnowledgeTopicSummary[];
}

export interface KnowledgeSection {
  heading: string;
  bullets: string[];
}

export interface KnowledgeTopicDetail {
  slug: string;
  title: string;
  summary: string;
  sections: KnowledgeSection[];
}

// ---------- 卡皮风险（POST /api/v1/risk-assessment） ----------

export type RiskAnswers = {
  last_shed_complete: 'complete' | 'partial_body' | 'large_retained';
  eye_condition: 'clear' | 'retained_spectacle';
  toe_condition: 'normal' | 'swollen' | 'discolored';
  hydration: 'daily' | 'occasional' | 'rarely_never';
  humidity: 'above_50' | '30_50' | 'below_30_unknown';
  water_bowl: 'fresh_daily' | 'stale_or_absent';
};

export interface RiskFactor {
  key: string;
  points: number;
  detail: string;
}

export interface RiskAssessmentResult {
  score: number;
  level: 'low' | 'moderate' | 'high';
  factors: RiskFactor[];
  vet_warning: string | null;
}
