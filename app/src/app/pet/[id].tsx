/**
 * 编辑宠物：从列表找当前宠物 → PetForm 预填 → useUpdatePet 保存 / useDeletePet 删除（Alert 确认）。
 */
import { router, useLocalSearchParams } from 'expo-router';
import { useMemo, useState } from 'react';
import { Alert, View, StyleSheet } from 'react-native';

import { PetForm, toPetInput, type PetFormValue } from '@/components/PetForm';
import { EmptyState, PageHeader, PrimaryButton, Screen } from '@/components/ui';
import { useDeletePet, usePets, useUpdatePet } from '@/hooks/usePets';

export default function EditPetScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const pets = usePets();
  const updatePet = useUpdatePet(id);
  const deletePet = useDeletePet(id);
  const [submitting, setSubmitting] = useState(false);

  const pet = useMemo(
    () => pets.data?.items.find((item) => item.id === id),
    [pets.data, id],
  );

  const initial = useMemo<PetFormValue | undefined>(
    () =>
      pet
        ? {
            name: pet.name,
            species: pet.species ?? '',
            morph: pet.morph ?? '',
            birth_date: pet.birth_date ?? '',
          }
        : undefined,
    [pet],
  );

  function confirmDelete(): void {
    Alert.alert('删除宠物', `确定要删除「${pet?.name ?? ''}」吗？它的蜕皮日志会一并删除，不可恢复。`, [
      { text: '取消', style: 'cancel' },
      {
        text: '删除',
        style: 'destructive',
        onPress: () => {
          void deletePet.mutateAsync().then(
            () => router.back(),
            (error) =>
              Alert.alert('删除失败', error instanceof Error ? error.message : String(error)),
          );
        },
      },
    ]);
  }

  if (pets.isPending) {
    return (
      <Screen>
        <PageHeader title="编辑宠物" />
      </Screen>
    );
  }

  if (!pet) {
    return (
      <Screen>
        <PageHeader title="编辑宠物" />
        <EmptyState icon="help-circle-outline" title="找不到这只宠物" subtitle="可能已被删除" />
      </Screen>
    );
  }

  async function handleSubmit(value: PetFormValue): Promise<void> {
    setSubmitting(true);
    try {
      await updatePet.mutateAsync(toPetInput(value));
      router.back();
    } catch (error) {
      Alert.alert('保存失败', error instanceof Error ? error.message : String(error));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Screen>
      <PageHeader title="编辑宠物" subtitle={pet.name} />
      <PetForm
        initial={initial}
        submitTitle="保存修改"
        submitting={submitting}
        onSubmit={(value) => void handleSubmit(value)}
        onCancel={() => router.back()}
      />
      <View style={styles.dangerZone}>
        <PrimaryButton title="删除宠物" danger onPress={confirmDelete} />
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  dangerZone: {
    marginTop: 8,
  },
});
