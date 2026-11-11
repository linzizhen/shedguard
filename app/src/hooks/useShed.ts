/**
 * 蜕皮日志与拍照查验 hooks。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as ImagePicker from 'expo-image-picker';

import { apiFetch } from '@/lib/api';
import { useServerUrl } from '@/lib/serverUrl';
import type {
  CheckPhotoResult,
  ShedRecord,
  ShedRecordInput,
  ShedRecordListResponse,
} from '@/lib/types';

export function useShedRecords(petId: string | null) {
  const serverUrl = useServerUrl();
  return useQuery({
    queryKey: ['shed-records', serverUrl, petId],
    queryFn: () =>
      apiFetch<ShedRecordListResponse>(`/api/v1/pets/${petId}/shed-records`),
    enabled: serverUrl !== '' && petId !== null,
  });
}

export function useCreateShedRecord(petId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: ShedRecordInput) =>
      apiFetch<ShedRecord>(`/api/v1/pets/${petId}/shed-records`, {
        method: 'POST',
        body: JSON.stringify(input),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['shed-records'] });
    },
  });
}

export function useUpdateShedRecord(petId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ recordId, input }: { recordId: string; input: ShedRecordInput }) =>
      apiFetch<ShedRecord>(`/api/v1/pets/${petId}/shed-records/${recordId}`, {
        method: 'PUT',
        body: JSON.stringify(input),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['shed-records'] });
    },
  });
}

export function useDeleteShedRecord(petId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (recordId: string) =>
      apiFetch<void>(`/api/v1/pets/${petId}/shed-records/${recordId}`, {
        method: 'DELETE',
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['shed-records'] });
    },
  });
}

/** 用系统相机拍一张（需相机权限） */
export async function takeCheckPhoto(): Promise<string | null> {
  const permission = await ImagePicker.requestCameraPermissionsAsync();
  if (!permission.granted) return null;
  const result = await ImagePicker.launchCameraAsync({
    mediaTypes: ['images'],
    quality: 0.8,
  });
  if (result.canceled || !result.assets[0]) return null;
  return result.assets[0].uri;
}

/** 从相册选一张（无需权限） */
export async function pickCheckPhoto(): Promise<string | null> {
  const result = await ImagePicker.launchImageLibraryAsync({
    mediaTypes: ['images'],
    quality: 0.8,
  });
  if (result.canceled || !result.assets[0]) return null;
  return result.assets[0].uri;
}

/** 上传照片做蜕皮查验（multipart） */
export async function checkPhoto(petId: string, uri: string): Promise<CheckPhotoResult> {
  const form = new FormData();
  form.append('file', { uri, name: 'check.jpg', type: 'image/jpeg' } as unknown as Blob);
  return apiFetch<CheckPhotoResult>(`/api/v1/pets/${petId}/check-photo`, {
    method: 'POST',
    body: form,
  });
}
