/**
 * 宠物的查询与增删改 hooks（React Query）。
 * 服务器地址变化时 queryKey 变化，自动重新拉取。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiFetch } from '@/lib/api';
import { useServerUrl } from '@/lib/serverUrl';
import type { Pet, PetListResponse } from '@/lib/types';

export interface PetInput {
  name: string;
  species?: string | null;
  morph?: string | null;
  birth_date?: string | null;
}

export function usePets() {
  const serverUrl = useServerUrl();
  return useQuery({
    queryKey: ['pets', serverUrl],
    queryFn: () => apiFetch<PetListResponse>('/api/v1/pets'),
    enabled: serverUrl !== '',
  });
}

export function useCreatePet() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: PetInput) =>
      apiFetch<Pet>('/api/v1/pets', {
        method: 'POST',
        body: JSON.stringify(input),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['pets'] });
    },
  });
}

export function useUpdatePet(petId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: PetInput) =>
      apiFetch<Pet>(`/api/v1/pets/${petId}`, {
        method: 'PUT',
        body: JSON.stringify(input),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['pets'] });
    },
  });
}

export function useDeletePet(petId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiFetch<void>(`/api/v1/pets/${petId}`, { method: 'DELETE' }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['pets'] });
    },
  });
}
