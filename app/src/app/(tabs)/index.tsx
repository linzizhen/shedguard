/**
 * 首页 = 拍照查验。只有一个动作：拍一张。
 * 不选宠物（只有一只时）、不显示置信度；结论用一句人话。
 */
import Ionicons from '@expo/vector-icons/Ionicons';
import { useMutation } from '@tanstack/react-query';
import { router } from 'expo-router';
import { useState } from 'react';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';

import { Card, EmptyState, PageHeader, PrimaryButton, Screen, SecondaryButton } from '@/components/ui';
import { usePets } from '@/hooks/usePets';
import { usePortraitToday } from '@/hooks/usePortraits';
import { checkPhoto, pickCheckPhoto, takeCheckPhoto } from '@/hooks/useShed';
import { portraitUrl } from '@/lib/auth';
import { resultCopy } from '@/lib/resultCopy';
import { useServerUrl } from '@/lib/serverUrl';
import { clayPress, clayShadow, colors, radius } from '@/lib/theme';
import type { CheckPhotoResult, Pet, ShedState } from '@/lib/types';

/** 详情折叠区里的状态名（给好奇的人看，主流程不出现） */
const DETAIL_LABEL: Record<ShedState, string> = {
  normal: '正常',
  opaque: '发白（快蜕皮）',
  shedding: '正在蜕皮',
  unknown: '看不清',
};

const TONE_COLOR: Record<string, string> = {
  shedding: colors.accent,
  wait: colors.warning,
  good: colors.success,
  unclear: colors.mutedForeground,
};

export default function HomeScreen() {
  const serverUrl = useServerUrl();
  const petsQuery = usePets();
  const [selectedPetId, setSelectedPetId] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<CheckPhotoResult | null>(null);
  const [showDetail, setShowDetail] = useState(false);
  const [errorText, setErrorText] = useState<string | null>(null);

  const checkMutation = useMutation({
    mutationFn: ({ petId, uri }: { petId: string; uri: string }) => checkPhoto(petId, uri),
    onSuccess: (data) => {
      setErrorText(null);
      setLastResult(data);
      setShowDetail(false);
    },
    onError: (error: Error) => {
      setErrorText('这张没传上去。检查一下网络，或者靠近一点再拍一张。');
      if (__DEV__) console.warn(error.message);
    },
  });

  const pets: Pet[] = petsQuery.data?.items ?? [];
  const activePetId =
    selectedPetId && pets.some((p) => p.id === selectedPetId) ? selectedPetId : (pets[0]?.id ?? null);
  const activePet = pets.find((p) => p.id === activePetId) ?? null;

  const portraitQuery = usePortraitToday(activePetId);
  const todayShot = portraitQuery.data?.items[0] ?? null;

  async function shoot(source: 'camera' | 'library') {
    if (!activePetId) return;
    const uri = source === 'camera' ? await takeCheckPhoto() : await pickCheckPhoto();
    if (!uri) return;
    checkMutation.mutate({ petId: activePetId, uri });
  }

  if (serverUrl === '') {
    return (
      <Screen>
        <PageHeader title="拍照" subtitle="拍一张它身上发白的地方" />
        <Card>
          <EmptyState
            icon="cloud-offline"
            title="App 还没连上电脑"
            subtitle="在「我的 → 高级设置」里填入电脑地址，或者重新打开首次引导。"
          />
        </Card>
        <PrimaryButton title="去填地址" onPress={() => router.replace('/welcome')} />
      </Screen>
    );
  }

  if (petsQuery.isLoading) {
    return (
      <Screen>
        <PageHeader title="拍照" subtitle="拍一张它身上发白的地方" />
        <Card>
          <EmptyState icon="hourglass" title="准备中…" />
        </Card>
      </Screen>
    );
  }

  if (pets.length === 0) {
    return (
      <Screen>
        <PageHeader title="拍照" subtitle="拍一张它身上发白的地方" />
        <Card style={{ gap: 12 }}>
          <EmptyState icon="paw" title="还没有你的守宫" subtitle="先花 10 秒建个档案，就能开始拍了" />
          <PrimaryButton title="创建档案" onPress={() => router.push('/pet/new')} />
        </Card>
      </Screen>
    );
  }

  const copy = lastResult ? resultCopy(lastResult.state) : null;
  const busy = checkMutation.isPending;

  return (
    <Screen>
      <PageHeader title="拍照" subtitle={activePet ? `正在给 ${activePet.name} 看皮肤` : '拍一张它身上发白的地方'} />

      {pets.length > 1 ? (
        <View style={styles.chips}>
          {pets.map((pet) => {
            const active = pet.id === activePetId;
            return (
              <Pressable
                key={pet.id}
                onPress={() => setSelectedPetId(pet.id)}
                accessibilityRole="button"
                accessibilityState={{ selected: active }}
                style={[styles.chip, active && styles.chipActive]}
              >
                <Text style={[styles.chipText, active && styles.chipTextActive]}>{pet.name}</Text>
              </Pressable>
            );
          })}
        </View>
      ) : null}

      {todayShot ? (
        <Pressable
          onPress={() =>
            router.push({ pathname: '/portrait/[id]', params: { id: todayShot.id } })
          }
          accessibilityRole="button"
          accessibilityLabel="查看今天的萌照"
          style={({ pressed }) => [pressed && clayPress]}
        >
          <Card style={styles.portraitCard}>
            <Image source={{ uri: portraitUrl(todayShot.id) }} style={styles.portraitThumb} />
            <View style={styles.portraitText}>
              <Text style={styles.portraitTitle}>今天的萌照</Text>
              <Text style={styles.portraitHint}>点开看看，不满意可以换一张</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color={colors.mutedForeground} />
          </Card>
        </Pressable>
      ) : null}

      <View style={styles.shutterWrap}>
        <Pressable
          onPress={() => void shoot('camera')}
          disabled={busy}
          accessibilityRole="button"
          accessibilityLabel="拍一张照片"
          style={({ pressed }) => [styles.shutter, busy && styles.shutterBusy, pressed && clayPress]}
        >
          <Ionicons name="camera" size={56} color="#FFFFFF" />
          <Text style={styles.shutterText}>{busy ? '正在看…' : '拍张照'}</Text>
        </Pressable>
        <Text style={styles.shutterHint}>
          {busy ? '正在看照片…（大约 3 秒）' : '把手机对准它，尽量靠近、光线亮一点'}
        </Text>
      </View>

      <SecondaryButton title="从相册选一张" onPress={() => void shoot('library')} disabled={busy} />

      {errorText ? (
        <Card>
          <Text style={styles.errorText}>{errorText}</Text>
        </Card>
      ) : null}

      {lastResult && copy ? (
        <Card style={styles.resultCard}>
          <View style={[styles.resultBadge, { backgroundColor: TONE_COLOR[copy.tone] }]}>
            <Ionicons name={copy.emojiIcon} size={18} color="#FFFFFF" />
            <Text style={styles.resultBadgeText}>结果</Text>
          </View>

          <Text style={styles.headline}>{copy.headline}</Text>
          <Text style={styles.advice}>{copy.advice}</Text>

          <PrimaryButton title="再拍一张" onPress={() => void shoot('camera')} disabled={busy} />
          <SecondaryButton title="记到蜕皮记录" onPress={() => router.push('/log')} />

          <Pressable
            onPress={() => setShowDetail((v) => !v)}
            accessibilityRole="button"
            style={styles.detailToggle}
          >
            <Text style={styles.detailToggleText}>
              {showDetail ? '收起细节' : '看看更多细节'}
            </Text>
          </Pressable>

          {showDetail ? (
            <View style={styles.detailBox}>
              <Text style={styles.detailLine}>
                判断：{DETAIL_LABEL[lastResult.state]}
                {lastResult.confidence !== null
                  ? `（把握 ${Math.round(lastResult.confidence * 100)}%）`
                  : '（没能给出把握程度）'}
              </Text>
              {lastResult.probabilities
                ? Object.entries(lastResult.probabilities)
                    .sort((a, b) => b[1] - a[1])
                    .map(([key, value]) => (
                      <Text key={key} style={styles.detailLine}>
                        {DETAIL_LABEL[key as ShedState] ?? key}：{Math.round(value * 100)}%
                      </Text>
                    ))
                : null}
              <Text style={styles.detailNote}>
                这些数字仅供了解，不影响上面那句结论。
              </Text>
            </View>
          ) : null}
        </Card>
      ) : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  portraitCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    padding: 10,
  },
  portraitThumb: {
    width: 72,
    height: 72,
    borderRadius: radius.md,
    backgroundColor: colors.background,
  },
  portraitText: {
    flex: 1,
    gap: 4,
  },
  portraitTitle: {
    fontSize: 17,
    fontWeight: '800',
    color: colors.foreground,
  },
  portraitHint: {
    fontSize: 13,
    color: colors.mutedForeground,
  },
  chips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  chip: {
    paddingHorizontal: 16,
    paddingVertical: 10,
    minHeight: 44,
    justifyContent: 'center',
    borderRadius: radius.md,
    borderWidth: 2,
    borderColor: colors.border,
    backgroundColor: colors.card,
  },
  chipActive: {
    backgroundColor: colors.primary,
    borderColor: colors.primaryDark,
  },
  chipText: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.mutedForeground,
  },
  chipTextActive: {
    color: '#FFFFFF',
  },
  shutterWrap: {
    alignItems: 'center',
    gap: 14,
    marginTop: 8,
  },
  shutter: {
    width: 200,
    height: 200,
    borderRadius: 100,
    backgroundColor: colors.primary,
    borderWidth: 5,
    borderColor: colors.primaryDark,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    ...clayShadow,
  },
  shutterBusy: {
    opacity: 0.7,
  },
  shutterText: {
    color: '#FFFFFF',
    fontSize: 20,
    fontWeight: '800',
  },
  shutterHint: {
    fontSize: 14,
    color: colors.mutedForeground,
    textAlign: 'center',
    paddingHorizontal: 24,
    lineHeight: 21,
  },
  errorText: {
    fontSize: 15,
    lineHeight: 22,
    color: colors.destructive,
  },
  resultCard: {
    gap: 12,
  },
  resultBadge: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    borderRadius: radius.md,
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  resultBadgeText: {
    color: '#FFFFFF',
    fontSize: 13,
    fontWeight: '800',
  },
  headline: {
    fontSize: 26,
    fontWeight: '800',
    color: colors.foreground,
  },
  advice: {
    fontSize: 16,
    lineHeight: 24,
    color: colors.foreground,
  },
  detailToggle: {
    paddingVertical: 10,
    minHeight: 44,
    justifyContent: 'center',
  },
  detailToggleText: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.primaryDark,
    textDecorationLine: 'underline',
  },
  detailBox: {
    backgroundColor: colors.background,
    borderRadius: radius.md,
    borderWidth: 2,
    borderColor: colors.border,
    padding: 12,
    gap: 6,
  },
  detailLine: {
    fontSize: 14,
    color: colors.foreground,
  },
  detailNote: {
    fontSize: 12,
    color: colors.mutedForeground,
    marginTop: 4,
  },
});
