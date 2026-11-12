/**
 * 拍照查验 Tab：选宠物 → 拍照/相册 → 上传 → 结果卡片。
 * 后端：POST /api/v1/pets/{id}/check-photo（multipart file）。
 */
import { useMutation } from '@tanstack/react-query';
import { router } from 'expo-router';
import { useState } from 'react';
import { Alert, StyleSheet, Text, View } from 'react-native';

import { PetPicker } from '@/components/PetPicker';
import { Card, EmptyState, PageHeader, PrimaryButton, Screen, SecondaryButton, SectionTitle } from '@/components/ui';
import { usePets } from '@/hooks/usePets';
import { checkPhoto, pickCheckPhoto, takeCheckPhoto } from '@/hooks/useShed';
import { useServerUrl } from '@/lib/serverUrl';
import { colors, radius } from '@/lib/theme';
import type { CheckPhotoResult, Pet, ShedState } from '@/lib/types';

/** 四状态的展示文案与配色 */
const STATE_META: Record<ShedState, { label: string; color: string; bg: string }> = {
  normal: { label: '状态正常', color: colors.success, bg: '#DCFCE7' },
  opaque: { label: '蒙白期', color: colors.warning, bg: '#FEF3C7' },
  shedding: { label: '蜕皮中', color: colors.accent, bg: '#DBEAFE' },
  unknown: { label: '无法判断', color: colors.mutedForeground, bg: colors.muted },
};

function ResultCard({ result, petName }: { result: CheckPhotoResult; petName: string }) {
  const meta = STATE_META[result.state];
  const probEntries = result.probabilities
    ? Object.entries(result.probabilities).sort((a, b) => b[1] - a[1])
    : [];
  return (
    <Card style={styles.resultCard}>
      <View style={styles.resultHeader}>
        <View style={[styles.stateBadge, { backgroundColor: meta.bg }]}>
          <Text style={[styles.stateBadgeText, { color: meta.color }]}>{meta.label}</Text>
        </View>
        {result.confidence !== null ? (
          <Text style={styles.confidenceText}>
            置信度 {(result.confidence * 100).toFixed(1)}%
          </Text>
        ) : null}
      </View>
      <Text style={styles.resultPet}>{petName}</Text>
      {probEntries.length > 0 ? (
        <View style={styles.probSection}>
          {probEntries.map(([state, value]) => {
            const m = STATE_META[state as ShedState];
            return (
              <View key={state} style={styles.probRow}>
                <Text style={styles.probLabel}>{m ? m.label : state}</Text>
                <View style={styles.probTrack}>
                  <View
                    style={[
                      styles.probFill,
                      { width: `${Math.round(value * 100)}%`, backgroundColor: m ? m.color : colors.mutedForeground },
                    ]}
                  />
                </View>
                <Text style={styles.probValue}>{(value * 100).toFixed(1)}%</Text>
              </View>
            );
          })}
        </View>
      ) : null}
      <View style={styles.adviceBox}>
        <Text style={styles.adviceText}>{result.advice}</Text>
      </View>
    </Card>
  );
}

export default function CheckScreen() {
  const serverUrl = useServerUrl();
  const petsQuery = usePets();
  const [selectedPetId, setSelectedPetId] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<CheckPhotoResult | null>(null);

  const checkMutation = useMutation({
    mutationFn: ({ petId, uri }: { petId: string; uri: string }) => checkPhoto(petId, uri),
    onSuccess: (data) => setLastResult(data),
    onError: (error: Error) => {
      Alert.alert('查验失败', error.message);
    },
  });

  const pets: Pet[] = petsQuery.data?.items ?? [];
  // 选中的宠物被删掉后回退到第一只
  const activePetId =
    selectedPetId && pets.some((p) => p.id === selectedPetId) ? selectedPetId : (pets[0]?.id ?? null);
  const activePet = pets.find((p) => p.id === activePetId) ?? null;

  async function handleTake() {
    if (!activePetId) return;
    const uri = await takeCheckPhoto();
    if (!uri) return;
    checkMutation.mutate({ petId: activePetId, uri });
  }

  async function handlePick() {
    if (!activePetId) return;
    const uri = await pickCheckPhoto();
    if (!uri) return;
    checkMutation.mutate({ petId: activePetId, uri });
  }

  if (serverUrl === '') {
    return (
      <Screen>
        <PageHeader title="拍照查验" subtitle="拍一张照片，看看它是不是要蜕皮了" />
        <Card>
          <EmptyState
            icon="cloud-offline"
            title="先配置服务器"
            subtitle="到「设置」页填写服务器地址，才能拍照查验"
          />
        </Card>
      </Screen>
    );
  }

  if (!petsQuery.data && petsQuery.isError) {
    return (
      <Screen>
        <PageHeader title="拍照查验" subtitle="拍一张照片，看看它是不是要蜕皮了" />
        <Card>
          <EmptyState icon="cloud-offline" title="无法加载宠物列表" subtitle={petsQuery.error.message} />
        </Card>
      </Screen>
    );
  }

  return (
    <Screen>
      <PageHeader title="拍照查验" subtitle="拍一张照片，看看它是不是要蜕皮了" />

      {petsQuery.isLoading ? (
        <Card>
          <EmptyState icon="hourglass" title="加载中…" />
        </Card>
      ) : pets.length === 0 ? (
        <Card style={{ gap: 12 }}>
          <EmptyState
            icon="paw"
            title="还没有添加宠物"
            subtitle="先添加一只宠物，再回来拍照查验"
          />
          <PrimaryButton title="添加宠物" onPress={() => router.push('/pet/new')} />
        </Card>
      ) : (
        <>
          <SectionTitle>选择宠物</SectionTitle>
          <PetPicker pets={pets} selectedId={activePetId} onSelect={setSelectedPetId} />

          <Card style={styles.cameraCard}>
            <EmptyState
              icon="camera"
              title={checkMutation.isPending ? '正在识别…' : '对准守宫拍一张'}
              subtitle={
                checkMutation.isPending
                  ? '照片已上传，正在检测与分类'
                  : '尽量让守宫占据画面中心，光线充足效果更好'
              }
            />
            <View style={styles.buttonRow}>
              <PrimaryButton
                title={checkMutation.isPending ? '识别中…' : '拍照'}
                onPress={() => void handleTake()}
                loading={checkMutation.isPending}
                style={styles.flex}
              />
              <SecondaryButton
                title="从相册选"
                onPress={() => void handlePick()}
                style={styles.flex}
              />
            </View>
          </Card>

          {lastResult && activePet ? <ResultCard result={lastResult} petName={activePet.name} /> : null}
        </>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  cameraCard: { gap: 16, paddingVertical: 24 },
  buttonRow: { flexDirection: 'row', gap: 12 },
  resultCard: { gap: 12 },
  resultHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  stateBadge: {
    borderRadius: radius.md,
    borderWidth: 2,
    borderColor: colors.border,
    paddingVertical: 6,
    paddingHorizontal: 14,
  },
  stateBadgeText: {
    fontSize: 16,
    fontWeight: '800',
  },
  confidenceText: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.mutedForeground,
  },
  resultPet: {
    fontSize: 13,
    color: colors.mutedForeground,
  },
  probSection: {
    gap: 8,
  },
  probRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  probLabel: {
    width: 64,
    fontSize: 13,
    fontWeight: '600',
    color: colors.foreground,
  },
  probTrack: {
    flex: 1,
    height: 10,
    borderRadius: 5,
    backgroundColor: colors.muted,
    overflow: 'hidden',
  },
  probFill: {
    height: '100%',
    borderRadius: 5,
  },
  probValue: {
    width: 52,
    fontSize: 12,
    textAlign: 'right',
    color: colors.mutedForeground,
  },
  adviceBox: {
    backgroundColor: colors.background,
    borderWidth: 2,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: 12,
  },
  adviceText: {
    fontSize: 14,
    lineHeight: 21,
    color: colors.foreground,
  },
});
