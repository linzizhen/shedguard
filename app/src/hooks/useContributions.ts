/**
 * 数据贡献（自愿分享）相关 hooks：设置、样本列表、撤回、导出。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiFetch } from '@/lib/api';
import { useServerUrl } from '@/lib/serverUrl';
import type {
  ContributionExport,
  ContributionListResponse,
  ContributionSetting,
  ContributionSettingsInput,
  ContributionUploadSummary,
} from '@/lib/types';

/** 分享开关；没保存过时服务端返回默认关闭。 */
export function useContributionSettings() {
  const serverUrl = useServerUrl();
  return useQuery({
    queryKey: ['contribution-settings', serverUrl],
    queryFn: () => apiFetch<ContributionSetting>('/api/v1/contribution-settings'),
    enabled: serverUrl !== '',
  });
}

/**
 * 用户改变主意时用：普通保存；开启时如果懒得等后台轮询，调用方可以再调 uploadNow。
 */
export function useUpdateContributionSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: ContributionSettingsInput) =>
      apiFetch<ContributionSetting>('/api/v1/contribution-settings', {
        method: 'PUT',
        body: JSON.stringify(input),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['contribution-settings'] });
    },
  });
}

/** 已分享的照片列表与统计数字。 */
export function useContributions(limit = 60) {
  const serverUrl = useServerUrl();
  return useQuery({
    queryKey: ['contributions', serverUrl, limit],
    queryFn: () => apiFetch<ContributionListResponse>(`/api/v1/contributions?limit=${limit}`),
    enabled: serverUrl !== '',
  });
}

/** 撤回某一张：本地删掉，远端也尽力删掉。 */
export function useWithdrawContribution() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sampleId: string) =>
      apiFetch<{ id: string }>(`/api/v1/contributions/${sampleId}/withdraw`, {
        method: 'POST',
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['contributions'] });
    },
  });
}

/** 打包一份 zip（用户想自己留档或想换种方式发给我们时用）。 */
export function useCreateContributionExport() {
  return useMutation({
    mutationFn: () =>
      apiFetch<ContributionExport>('/api/v1/contributions/export', { method: 'POST' }),
  });
}

/** 手动催一次上传；没配收件箱时服务端会返回 skipped，不会假装成功。 */
export function useUploadContributionsNow() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<ContributionUploadSummary>('/api/v1/contributions/upload-now', {
        method: 'POST',
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['contributions'] });
    },
  });
}
