/**
 * 萌照相关 hooks：今日、相册、设置与反馈。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiFetch } from '@/lib/api';
import { useServerUrl } from '@/lib/serverUrl';
import type {
  PortraitFeedbackInput,
  PortraitListResponse,
  PortraitSetting,
  PortraitShot,
} from '@/lib/types';

/** 今天的萌照（可能还没到拍摄时间，返回空数组）。 */
export function usePortraitToday(petId: string | null) {
  const serverUrl = useServerUrl();
  return useQuery({
    queryKey: ['portraits-today', serverUrl, petId ?? ''],
    queryFn: () => apiFetch<PortraitListResponse>(`/api/v1/pets/${petId}/portraits/today`),
    enabled: serverUrl !== '' && petId !== null,
    refetchInterval: 120_000,
  });
}

/** 相册：最近若干天的萌照。 */
export function usePortraitAlbum(petId: string | null, limit = 60) {
  const serverUrl = useServerUrl();
  return useQuery({
    queryKey: ['portraits-album', serverUrl, petId ?? '', limit],
    queryFn: () =>
      apiFetch<PortraitListResponse>(`/api/v1/pets/${petId}/portraits?limit=${limit}`),
    enabled: serverUrl !== '' && petId !== null,
  });
}

/** 单张萌照（从相册或提醒点进来时用）。 */
export function usePortrait(shotId: string | null, album: PortraitShot[] | undefined) {
  const found = (album ?? []).find((item) => item.id === shotId) ?? null;
  return found;
}

/** 萌照设置；没有保存过时服务端会返回默认值。 */
export function usePortraitSettings(petId: string | null) {
  const serverUrl = useServerUrl();
  return useQuery({
    queryKey: ['portrait-settings', serverUrl, petId ?? ''],
    queryFn: () => apiFetch<PortraitSetting>(`/api/v1/pets/${petId}/portrait-settings`),
    enabled: serverUrl !== '' && petId !== null,
  });
}

export function useUpdatePortraitSettings(petId: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: Partial<Omit<PortraitSetting, 'pet_id' | 'updated_at_utc'>>) =>
      apiFetch<PortraitSetting>(`/api/v1/pets/${petId}/portrait-settings`, {
        method: 'PUT',
        body: JSON.stringify(input),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['portrait-settings'] });
    },
  });
}

/** 「这张好看」/「换一张」反馈。 */
export function usePortraitFeedback() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ shotId, input }: { shotId: string; input: PortraitFeedbackInput }) =>
      apiFetch<{ id: string }>(`/api/v1/portraits/${shotId}/feedback`, {
        method: 'POST',
        body: JSON.stringify(input),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['portraits-album'] });
    },
  });
}