/**
 * 首页 = 拍照查验。纸感极简（P34）。
 *
 * 只有一个主动作：拍一张。不选宠物（只有一只时）、不显示置信度；结论用一句人话。
 * 视觉：纸底 + 近黑实心圆快门 + 1px 纸线分层，不用卡片边框与阴影。
 */
import Ionicons from '@expo/vector-icons/Ionicons';
import { useMutation } from '@tanstack/react-query';
import { router } from 'expo-router';
import { useState } from 'react';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';

import {
  Badge,
  BrandBar,
  Divider,
  EmptyState,
  Group,
  Hint,
  IconButton,
  Marker,
  Note,
  PageHeader,
  PrimaryButton,
  Screen,
  TextLink,
} from '@/components/ui';
import { useAlerts } from '@/hooks/useAlerts';
import { usePets } from '@/hooks/usePets';
import { usePortraitToday } from '@/hooks/usePortraits';
import { checkPhoto, pickCheckPhoto, takeCheckPhoto } from '@/hooks/useShed';
import { portraitUrl } from '@/lib/auth';
import { alertTitle, resultCopy } from '@/lib/resultCopy';
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
  // 徽标要能配上四条质量原因（太糊/太暗/过曝/没找到守宫），所以不能写「没看清」——
  // 「没找到守宫」+「没看清」会自相矛盾，用中性的「先重拍」。
  unclear: '先重拍',
};

/** 把 ISO 时间转成「今天 08:24 / 11月18日 08:24」 */
function shortMoment(iso: string | null): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  const now = new Date();
  const sameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate();
  const hh = `${date.getHours()}`.padStart(2, '0');
  const mm = `${date.getMinutes()}`.padStart(2, '0');
  if (sameDay) return `今天 ${hh}:${mm}`;
  return `${date.getMonth() + 1}月${date.getDate()}日 ${hh}:${mm}`;
}

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
        setErrorText('连不上服务端。确认地址没填错，网络是通的。');
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

  const alertsQuery = useAlerts({ petId: activePetId });
  const latestAlert = alertsQuery.data?.items.find((a) => a.read_at_utc === null) ?? null;

  async function shoot(source: 'camera' | 'library') {
    if (!activePetId) return;
    const uri = source === 'camera' ? await takeCheckPhoto() : await pickCheckPhoto();
    if (!uri) return;
    checkMutation.mutate({ petId: activePetId, uri });
  }

  if (serverUrl === '') {
    return (
      <Screen>
        <BrandBar />
        <PageHeader title="拍照" subtitle="拍一张它身上发白的地方" />
        <EmptyState
          title="还没连上服务端"
          subtitle="在「我的 → 高级设置」里填入地址，或者重新打开首次引导。"
        />
        <PrimaryButton title="去填地址" onPress={() => router.replace('/welcome')} />
      </Screen>
    );
  }

  if (petsQuery.isLoading) {
    return (
      <Screen>
        <BrandBar />
        <PageHeader title="拍照" subtitle="拍一张它身上发白的地方" />
        <EmptyState title="准备中…" />
      </Screen>
    );
  }

  if (pets.length === 0) {
    return (
      <Screen>
        <BrandBar />
        <PageHeader title="拍照" subtitle="拍一张它身上发白的地方" />
        <EmptyState title="还没有你的守宫" subtitle="先花 10 秒建个档案，就能开始拍了" />
        <PrimaryButton title="创建档案" onPress={() => router.push('/pet/new')} />
      </Screen>
    );
  }

  const copy = lastResult ? resultCopy(lastResult.state, lastResult.quality_reason) : null;
  const busy = checkMutation.isPending;

  return (
    <Screen>
      <BrandBar
        right={
          <Pressable
            onPress={() => router.push('/settings')}
            accessibilityRole="button"
            accessibilityLabel="打开我的"
            hitSlop={8}
          >
            <View style={styles.avatar}>
              <Ionicons name="person" size={15} color={colors.mutedForeground} />
            </View>
          </Pressable>
        }
      />

      <View style={styles.pageHead}>
        <Text style={styles.pageTitle}>今天看一眼</Text>
        <Note style={styles.pageSubtitle}>
          {activePet
            ? `${activePet.name}的皮肤有没有发白，拍一张就知道。`
            : '它的皮肤有没有发白，拍一张就知道。'}
        </Note>
      </View>

      {pets.length > 1 ? (
        <Group>
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
        </Group>
      ) : null}

      <View style={styles.shutterBlock}>
        <Hint style={styles.shutterHint}>
          {busy ? '正在看照片…（大约 3 秒）' : '对准它、靠近一点，光线亮一点更准'}
        </Hint>

        <Pressable
          onPress={() => void shoot('camera')}
          disabled={busy}
          accessibilityRole="button"
          accessibilityLabel="拍一张照片"
          style={({ pressed }) => [styles.shutter, busy && styles.busy, pressed && clayPress]}
        >
          <Ionicons name="camera-outline" size={32} color={colors.onPrimary} />
          <Text style={styles.shutterText}>{busy ? '正在看…' : '拍照'}</Text>
        </Pressable>

        <View style={styles.actionRow}>
          <IconButton icon="image-outline" title="从相册选" onPress={() => void shoot('library')} />
          <IconButton
            icon="videocam-outline"
            title="接摄像头"
            onPress={() => router.push('/cameras')}
          />
        </View>
      </View>

      {errorText ? (
        <View style={styles.errorBox}>
          <Marker tone="danger" />
          <Text style={styles.errorText}>{errorText}</Text>
        </View>
      ) : null}

      {lastResult && copy ? (
        <View style={styles.resultBlock}>
          <Divider />
          <View style={styles.resultTop}>
            <Text style={styles.eyebrow}>这一次</Text>
            <Badge
              label={TONE_LABEL[copy.tone] ?? '结果'}
              tone={TONE_BADGE[copy.tone] ?? 'neutral'}
            />
          </View>
          <Text style={styles.headline}>{copy.headline}</Text>
          <Note>{copy.advice}</Note>

          <View style={styles.resultActions}>
            <PrimaryButton title="再拍一张" onPress={() => void shoot('camera')} disabled={busy} />
            <IconButton icon="bookmark-outline" title="记到记录" onPress={() => router.push('/log')} />
          </View>

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
              size={13}
              color={colors.faintForeground}
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
                      <Hint key={key}>
                        {DETAIL_LABEL[key as ShedState] ?? key}：{Math.round(value * 100)}%
                      </Hint>
                    ))
                : null}
              <Text style={styles.detailNote}>这些数字仅供了解，不影响上面那句结论。</Text>
            </View>
          ) : null}
        </View>
      ) : null}

      {todayShot ? (
        <Pressable
          onPress={() => router.push({ pathname: '/portrait/[id]', params: { id: todayShot.id } })}
          accessibilityRole="button"
          accessibilityLabel="查看今天的萌照"
          style={({ pressed }) => [styles.portraitRow, pressed && clayPress]}
        >
          <Image source={{ uri: portraitUrl(todayShot.id) }} style={styles.portraitThumb} />
          <View style={styles.portraitText}>
            <Text style={styles.portraitTitle}>今天的萌照</Text>
            <Hint>点开看看，不满意可以换一张</Hint>
          </View>
          <Ionicons name="chevron-forward" size={17} color={colors.ghostForeground} />
        </Pressable>
      ) : null}

      <Group>
        <View style={styles.sectionHead}>
          <Text style={styles.eyebrow}>上一次</Text>
          <TextLink title="全部记录" onPress={() => router.push('/log')} />
        </View>

        {latestAlert ? (
          <View style={styles.lastBlock}>
            <View style={styles.lastTitleRow}>
              <Marker />
              <Text style={styles.lastTitle}>
                {alertTitle(latestAlert.kind, activePet?.name ?? null)}
              </Text>
            </View>
            <Note>
              {latestAlert.kind === 'shedding_detected'
                ? '记得把水盆加满，保持湿润。别去帮它撕。'
                : '点开看看具体情况。'}
            </Note>
            <Text style={styles.lastTime}>{shortMoment(latestAlert.created_at_utc)}</Text>
          </View>
        ) : (
          <Hint>还没有提醒。拍一张，或者接上摄像头让它自己盯着。</Hint>
        )}
      </Group>
    </Screen>
  );
}

const styles = StyleSheet.create({
  avatar: {
    width: 34,
    height: 34,
    borderRadius: radius.pill,
    backgroundColor: colors.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pageHead: {
    marginTop: space.lg,
    gap: space.tight,
  },
  pageTitle: {
    ...type.display,
    color: colors.foreground,
  },
  pageSubtitle: {
    maxWidth: 320,
  },
  chips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: space.sm,
  },
  chip: {
    paddingHorizontal: space.lg,
    minHeight: 38,
    justifyContent: 'center',
    borderRadius: radius.pill,
    borderWidth: hairline,
    borderColor: colors.border,
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
    color: colors.onPrimary,
  },
  shutterBlock: {
    alignItems: 'center',
    gap: space.xxxl,
    paddingTop: space.xxxl,
    paddingBottom: space.xxxl,
  },
  shutter: {
    width: 172,
    height: 172,
    borderRadius: radius.pill,
    backgroundColor: colors.foreground,
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.sm,
    ...shadow.raised,
  },
  busy: {
    opacity: 0.7,
  },
  shutterText: {
    ...type.button,
    color: colors.onPrimary,
    letterSpacing: 1.6,
  },
  shutterHint: {
    textAlign: 'center',
  },
  actionRow: {
    flexDirection: 'row',
    gap: space.sm,
    alignSelf: 'stretch',
  },
  errorBox: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: space.md,
    backgroundColor: colors.destructiveSoft,
    borderRadius: radius.lg,
    padding: space.lg,
  },
  errorText: {
    ...type.note,
    flex: 1,
    color: colors.destructive,
  },
  resultBlock: {
    gap: space.tight,
    paddingTop: space.xs,
  },
  resultTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  eyebrow: {
    ...type.label,
    color: colors.faintForeground,
  },
  headline: {
    ...type.title,
    color: colors.foreground,
  },
  resultActions: {
    flexDirection: 'row',
    gap: space.sm,
    alignItems: 'stretch',
  },
  detailToggle: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.xs,
    paddingVertical: space.sm,
    minHeight: 36,
  },
  detailToggleText: {
    ...type.caption,
    fontWeight: '600',
    color: colors.faintForeground,
  },
  detailBox: {
    backgroundColor: colors.muted,
    borderRadius: radius.md,
    padding: space.md,
    gap: space.xs,
  },
  detailLine: {
    ...type.note,
    color: colors.body,
  },
  detailNote: {
    ...type.hint,
    color: colors.ghostForeground,
    marginTop: space.xs,
  },
  portraitRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.md,
  },
  portraitThumb: {
    width: 56,
    height: 56,
    borderRadius: radius.sm,
    backgroundColor: colors.muted,
  },
  portraitText: {
    flex: 1,
    gap: space.xxs,
  },
  portraitTitle: {
    ...type.heading,
    color: colors.foreground,
  },
  sectionHead: {
    flexDirection: 'row',
    alignItems: 'baseline',
    justifyContent: 'space-between',
  },
  lastBlock: {
    gap: space.tight,
  },
  lastTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
  },
  lastTitle: {
    ...type.heading,
    color: colors.foreground,
  },
  lastTime: {
    ...type.hint,
    color: colors.ghostForeground,
    letterSpacing: 0.3,
  },
});
