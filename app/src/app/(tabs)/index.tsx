/**
 * 首页 = 拍照查验。只有一个动作：拍一张。
 * 不选宠物（只有一只时）、不显示置信度；结论用一句人话。
 */
import Ionicons from '@expo/vector-icons/Ionicons';
import { useMutation } from '@tanstack/react-query';
import { router } from 'expo-router';
import { useState } from 'react';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';

import {
  Badge,
  Card,
  EmptyState,
  PageHeader,
  PrimaryButton,
  Screen,
  SecondaryButton,
} from '@/components/ui';
import { usePets } from '@/hooks/usePets';
import { usePortraitToday } from '@/hooks/usePortraits';
import { checkPhoto, pickCheckPhoto, takeCheckPhoto } from '@/hooks/useShed';
import { portraitUrl } from '@/lib/auth';
import { resultCopy } from '@/lib/resultCopy';
import { useServerUrl } from '@/lib/serverUrl';
import { clayPress, colors, hairline, radius, shadow, space, type } from '@/lib/theme';
import type { CheckPhotoResult, Pet, ShedState } from '@/lib/types';

/** 详情折叠区里的状态名（给好奇的人看，主流程不出现） */
const DETAIL_LABEL: Record<ShedState, string> = {
  normal: '正常',
  opaque: '发白（快蜕皮）',
  shedding: '正在蜕皮',
  unknown: '看不清',
};

const TONE_BADGE: Record<string, 'accent' | 'warning' | 'success' | 'neutral'> = {
  shedding: 'accent',
  wait: 'warning',
  good: 'success',
  unclear: 'neutral',
};

const TONE_LABEL: Record<string, string> = {
  shedding: '正在蜕皮',
  wait: '快蜕皮了',
  good: '状态正常',
  unclear: '没看清',
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
      const message = error.message ?? '';
      if (message.includes('太大') || message.includes('PAYLOAD_TOO_LARGE')) {
        setErrorText('这张照片太大了。换一张小一点的，或者用手机自带编辑器裁一下再试。');
      } else if (message.includes('格式') || message.includes('UNSUPPORTED_MEDIA_TYPE')) {
        setErrorText('这个格式看不了。换成 JPG 或 PNG 再试一次。');
      } else if (message.includes('无法连接') || message.includes('网络')) {
        setErrorText('连不上电脑上的程序。确认手机和电脑在同一个 Wi-Fi，地址也没填错。');
      } else {
        setErrorText('这张没传上去。再试一次，或者换一张。');
      }
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
            icon="cloud-offline-outline"
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
          <EmptyState icon="hourglass-outline" title="准备中…" />
        </Card>
      </Screen>
    );
  }

  if (pets.length === 0) {
    return (
      <Screen>
        <PageHeader title="拍照" subtitle="拍一张它身上发白的地方" />
        <Card style={{ gap: space.md }}>
          <EmptyState
            icon="paw-outline"
            title="还没有你的守宫"
            subtitle="先花 10 秒建个档案，就能开始拍了"
          />
          <PrimaryButton title="创建档案" onPress={() => router.push('/pet/new')} />
        </Card>
      </Screen>
    );
  }

  const copy = lastResult ? resultCopy(lastResult.state) : null;
  const busy = checkMutation.isPending;

  return (
    <Screen>
      <PageHeader
        title="拍照"
        subtitle={activePet ? `正在给 ${activePet.name} 看皮肤` : '拍一张它身上发白的地方'}
      />

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
            <Ionicons name="chevron-forward" size={18} color={colors.faintForeground} />
          </Card>
        </Pressable>
      ) : null}

      <View style={styles.shutterWrap}>
        <Pressable
          onPress={() => void shoot('camera')}
          disabled={busy}
          accessibilityRole="button"
          accessibilityLabel="拍一张照片"
          style={({ pressed }) => [styles.shutterRing, busy && styles.busy, pressed && clayPress]}
        >
          <View style={styles.shutter}>
            <Ionicons name="camera" size={40} color="#FFFFFF" />
            <Text style={styles.shutterText}>{busy ? '正在看…' : '拍张照'}</Text>
          </View>
        </Pressable>
        <Text style={styles.shutterHint}>
          {busy ? '正在看照片…（大约 3 秒）' : '把手机对准它，尽量靠近、光线亮一点'}
        </Text>
      </View>

      <SecondaryButton title="从相册选一张" onPress={() => void shoot('library')} disabled={busy} />

      {errorText ? (
        <Card tone="soft" style={styles.errorCard}>
          <Ionicons name="alert-circle" size={20} color={colors.destructive} />
          <Text style={styles.errorText}>{errorText}</Text>
        </Card>
      ) : null}

      {lastResult && copy ? (
        <Card style={styles.resultCard}>
          <View style={styles.resultTop}>
            <Badge label={TONE_LABEL[copy.tone] ?? '结果'} tone={TONE_BADGE[copy.tone] ?? 'neutral'} />
            <Text style={styles.resultDate}>{lastResult.state === 'unknown' ? '再看看' : '刚刚'}</Text>
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
            <Ionicons
              name={showDetail ? 'chevron-up' : 'chevron-down'}
              size={14}
              color={colors.mutedForeground}
            />
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
              <Text style={styles.detailNote}>这些数字仅供了解，不影响上面那句结论。</Text>
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
    gap: space.md,
    padding: space.md,
  },
  portraitThumb: {
    width: 60,
    height: 60,
    borderRadius: radius.md,
    backgroundColor: colors.muted,
  },
  portraitText: {
    flex: 1,
    gap: 2,
  },
  portraitTitle: {
    ...type.heading,
    color: colors.foreground,
  },
  portraitHint: {
    ...type.caption,
    color: colors.mutedForeground,
  },
  chips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: space.sm,
  },
  chip: {
    paddingHorizontal: space.lg,
    minHeight: 40,
    justifyContent: 'center',
    borderRadius: radius.pill,
    borderWidth: hairline,
    borderColor: colors.border,
    backgroundColor: colors.card,
  },
  chipActive: {
    backgroundColor: colors.foreground,
    borderColor: colors.foreground,
  },
  chipText: {
    ...type.caption,
    fontWeight: '600',
    color: colors.mutedForeground,
  },
  chipTextActive: {
    color: '#FFFFFF',
  },
  shutterWrap: {
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.lg,
  },
  shutterRing: {
    width: 196,
    height: 196,
    borderRadius: radius.pill,
    borderWidth: hairline,
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.card,
  },
  shutter: {
    width: 168,
    height: 168,
    borderRadius: radius.pill,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.sm,
    ...shadow.raised,
  },
  busy: {
    opacity: 0.75,
  },
  shutterText: {
    color: '#FFFFFF',
    fontSize: 18,
    fontWeight: '800',
    letterSpacing: 0.2,
  },
  shutterHint: {
    ...type.caption,
    color: colors.mutedForeground,
    textAlign: 'center',
    paddingHorizontal: space.xxl,
  },
  errorCard: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: space.md,
    backgroundColor: colors.destructiveSoft,
    borderColor: colors.destructiveSoft,
  },
  errorText: {
    ...type.bodySm,
    flex: 1,
    color: colors.destructive,
  },
  resultCard: {
    gap: space.md,
  },
  resultTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  resultDate: {
    ...type.caption,
    color: colors.faintForeground,
  },
  headline: {
    ...type.title,
    color: colors.foreground,
  },
  advice: {
    ...type.body,
    color: colors.body,
  },
  detailToggle: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    paddingVertical: space.sm,
    minHeight: 40,
  },
  detailToggleText: {
    ...type.caption,
    fontWeight: '700',
    color: colors.mutedForeground,
  },
  detailBox: {
    backgroundColor: colors.muted,
    borderRadius: radius.md,
    padding: space.md,
    gap: space.xs,
  },
  detailLine: {
    ...type.caption,
    color: colors.body,
  },
  detailNote: {
    ...type.caption,
    fontSize: 12,
    color: colors.faintForeground,
    marginTop: space.xs,
  },
});
