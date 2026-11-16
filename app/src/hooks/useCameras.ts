/**
 * 摄像头相关 hooks：列表、增删改、测试连接、抓一张看看。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiFetch } from '@/lib/api';
import { useServerUrl } from '@/lib/serverUrl';
import type {
  CameraCreateInput,
  CameraItem,
  CameraListResponse,
  CameraTestResult,
  CameraUpdateInput,
} from '@/lib/types';

export function useCameras() {
  const serverUrl = useServerUrl();
  return useQuery({
    queryKey: ['cameras', serverUrl],
    queryFn: () => apiFetch<CameraListResponse>('/api/v1/cameras'),
    enabled: serverUrl !== '',
  });
}

export function useCreateCamera() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CameraCreateInput) =>
      apiFetch<CameraItem>('/api/v1/cameras', {
        method: 'POST',
        body: JSON.stringify(input),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['cameras'] });
    },
  });
}

export function useUpdateCamera(cameraId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CameraUpdateInput) =>
      apiFetch<CameraItem>(`/api/v1/cameras/${cameraId}`, {
        method: 'PATCH',
        body: JSON.stringify(input),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['cameras'] });
    },
  });
}

export function useDeleteCamera() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (cameraId: string) =>
      apiFetch<void>(`/api/v1/cameras/${cameraId}`, { method: 'DELETE' }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['cameras'] });
    },
  });
}

/** 连一下试试：不入库，只看能不能取到画面。 */
export function useTestCamera() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (cameraId: string) =>
      apiFetch<CameraTestResult>(`/api/v1/cameras/${cameraId}/test`, { method: 'POST' }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['cameras'] });
    },
  });
}

/** 现在拍一张：会入库并走完整判定流水线。 */
export function useCameraSnapshot() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (cameraId: string) =>
      apiFetch<{ image_id: string; duplicate: boolean }>(
        `/api/v1/cameras/${cameraId}/snapshot`,
        { method: 'POST' },
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['cameras'] });
      void queryClient.invalidateQueries({ queryKey: ['alerts'] });
      void queryClient.invalidateQueries({ queryKey: ['portraits-today'] });
    },
  });
}