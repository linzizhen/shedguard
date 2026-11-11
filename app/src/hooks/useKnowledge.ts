/**
 * 知识库查询 hooks（静态内容，可长缓存）。
 */
import { useQuery } from '@tanstack/react-query';

import { apiFetch } from '@/lib/api';
import { useServerUrl } from '@/lib/serverUrl';
import type { KnowledgeTopicDetail, KnowledgeTopicListResponse } from '@/lib/types';

export function useKnowledgeTopics() {
  const serverUrl = useServerUrl();
  return useQuery({
    queryKey: ['knowledge-topics', serverUrl],
    queryFn: () => apiFetch<KnowledgeTopicListResponse>('/api/v1/knowledge/topics'),
    enabled: serverUrl !== '',
    staleTime: 24 * 60 * 60 * 1000,
  });
}

export function useKnowledgeTopic(slug: string) {
  const serverUrl = useServerUrl();
  return useQuery({
    queryKey: ['knowledge-topic', serverUrl, slug],
    queryFn: () => apiFetch<KnowledgeTopicDetail>(`/api/v1/knowledge/topics/${slug}`),
    enabled: serverUrl !== '',
    staleTime: 24 * 60 * 60 * 1000,
  });
}
