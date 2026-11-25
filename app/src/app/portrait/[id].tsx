/**
 * 一张萌照的详情页：看大图、说「好看」或「不太满意」。
 *
 * V1 不做手动框头（需要拖拽交互），只把反馈记下来，供后续训练偏好模型用。
 * 纸感极简（P34）：照片直接铺开，反馈用 Marker + 一行小字。
 */
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { Image, StyleSheet, Text, View } from 'react-native';

import { Divider, Marker, PrimaryButton, Screen, SecondaryButton } from '@/components/ui';
import { usePortraitFeedback } from '@/hooks/usePortraits';
import { ensureToken, portraitUrl } from '@/lib/auth';
import { formatDateCn } from '@/lib/dates';
import { colors, radius, space, type } from '@/lib/theme';

export default function PortraitScreen() {
  const params = useLocalSearchParams<{ id: string; local_date?: string }>();
  const shotId = params.id ?? '';
  const feedback = usePortraitFeedback();
  const [said, setSaid] = useState<'like' | 'skip' | null>(null);
  const [tokenReady, setTokenReady] = useState(false);

  useEffect(() => {
    // 图片地址用 ?token= 鉴权，令牌就绪后再渲染，否则会拿到空图。
    void ensureToken()
      .then(() => setTokenReady(true))
      .catch(() => setTokenReady(true));
  }, []);

  function send(kind: 'like' | 'skip') {
    if (!shotId) return;
    feedback.mutate({ shotId, input: { kind } }, { onSuccess: () => setSaid(kind) });
  }

  return (
    <Screen>
      <Text style={styles.subtitle}>
        {params.local_date ? `${formatDateCn(params.local_date)} · 它今天的样子` : '它今天的样子'}
      </Text>

      <Divider />

      {tokenReady && shotId ? (
        <Image source={{ uri: portraitUrl(shotId) }} style={styles.image} resizeMode="contain" />
      ) : (
        <View style={styles.imagePlaceholder}>
          <Text style={styles.placeholderText}>照片加载中…</Text>
        </View>
      )}

      {said === 'like' ? (
        <View style={styles.tipRow}>
          <Marker tone="success" />
          <Text style={styles.tipText}>记下了。之后会多挑这样的角度。</Text>
        </View>
      ) : null}

      {said === 'skip' ? (
        <View style={styles.tipRow}>
          <Marker />
          <Text style={styles.tipText}>记下了。下次会尽量换一张更好的。</Text>
        </View>
      ) : null}

      {said === null ? (
        <>
          <PrimaryButton
            title="这张好看"
            onPress={() => send('like')}
            disabled={feedback.isPending}
          />
          <SecondaryButton
            title="不太满意"
            onPress={() => send('skip')}
            disabled={feedback.isPending}
          />
        </>
      ) : (
        <SecondaryButton title="回去看看别的" onPress={() => router.back()} />
      )}

      <Text style={styles.hint}>
        照片是设备定时拍的。把摄像头放近一点、光线亮一点，拍出来会更清楚。
      </Text>
    </Screen>
  );
}

const styles = StyleSheet.create({
  subtitle: {
    ...type.bodySm,
    color: colors.mutedForeground,
  },
  image: {
    width: '100%',
    aspectRatio: 1,
    borderRadius: radius.sm,
    backgroundColor: colors.muted,
  },
  imagePlaceholder: {
    width: '100%',
    aspectRatio: 1,
    borderRadius: radius.sm,
    backgroundColor: colors.muted,
    alignItems: 'center',
    justifyContent: 'center',
  },
  placeholderText: {
    ...type.bodySm,
    color: colors.mutedForeground,
  },
  tipRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
  },
  tipText: {
    flex: 1,
    ...type.bodySm,
    color: colors.body,
  },
  hint: {
    ...type.caption,
    color: colors.faintForeground,
  },
});
