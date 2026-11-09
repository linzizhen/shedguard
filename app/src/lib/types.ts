/**
 * 后端领域对象在 App 侧的镜像（只放当前用到的字段）。
 * 字段与 server/src/shedguard_server/api/routes/pets.py 的序列化保持一致。
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
