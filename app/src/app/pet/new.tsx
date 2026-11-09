/**
 * 添加宠物：PetForm + useCreatePet，成功后返回。
 */
import { router } from 'expo-router';
import { useState } from 'react';
import { Alert } from 'react-native';

import { PetForm, toPetInput, type PetFormValue } from '@/components/PetForm';
import { PageHeader, Screen } from '@/components/ui';
import { useCreatePet } from '@/hooks/usePets';

export default function NewPetScreen() {
  const createPet = useCreatePet();
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(value: PetFormValue): Promise<void> {
    setSubmitting(true);
    try {
      await createPet.mutateAsync(toPetInput(value));
      router.back();
    } catch (error) {
      Alert.alert('保存失败', error instanceof Error ? error.message : String(error));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Screen>
      <PageHeader title="添加宠物" subtitle="建立守宫档案，开始记录它的蜕皮周期" />
      <PetForm
        submitTitle="保存"
        submitting={submitting}
        onSubmit={(value) => void handleSubmit(value)}
        onCancel={() => router.back()}
      />
    </Screen>
  );
}
