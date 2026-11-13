/**
 * 一张萌照的详情页：看大图、说「好看」或「不太满意」。
 *
 * V1 不做手动框头（需要拖拽交互），只把反馈记下来，供后续训练偏好模型用。
 */
import Ionicons from '@expo/vector-icons/Ionicons';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { Image, StyleSheet, Text, View } from 'react-native';

import { Card, PrimaryButton, Screen, SecondaryButton } from '@/components/ui';
import { usePortraitFeedback } from '@/hooks/usePortraits';
import { ensureToken, portraitUrl } from '@/lib/auth';
import { formatDateCn } from '@/lib/dates';
import { colors, radius } from '@/lib/theme';

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
    feedback.mutate(
      { shotId, input: { kind } },
      { onSuccess: () => setSaid(kind) },
    );
  }

  return (
    <Screen>
      <Text style={styles.subtitle}>
        {params.local_date ? `${formatDateCn(params.local_date)} · 它今天的样子` : '它今天的样子'}
      </Text>

      <Card style={styles.imageCard}>
        {tokenReady && shotId ? (
          <Image source={{ uri: portraitUrl(shotId) }} style={styles.image} resizeMode="contain" />
        ) : (
          <View style={styles.imagePlaceholder}>
            <Text style={styles.placeholderText}>照片加载中…</Text>
          </View>
        )}
      </Card>

      {said === 'like' ? (
        <Card style={styles.tipCard}>
          <View style={styles.tipRow}>
            <Ionicons name="heart" size={20} color={colors.primary} />
            <Text style={styles.tipText}>记下了。之后会多挑这样的角度。</Text>
          </View>
        </Card>
      ) : null}

      {said === 'skip' ? (
        <Card style={styles.tipCard}>
          <View style={styles.tipRow}>
            <Ionicons name="refresh" size={20} color={colors.mutedForeground} />
            <Text style={styles.tipText}>记下了。下次会尽量换一张更好的。</Text>
          </View>
        </Card>
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
    fontSize: 14,
    color: colors.mutedForeground,
  },
  imageCard: {
    padding: 8,
  },
  image: {
    width: '100%',
    aspectRatio: 1,
    borderRadius: radius.md,
    backgroundColor: colors.background,
  },
  imagePlaceholder: {
    width: '100%',
    aspectRatio: 1,
    borderRadius: radius.md,
    backgroundColor: colors.background,
    alignItems: 'center',
    justifyContent: 'center',
  },
  placeholderText: {
    fontSize: 14,
    color: colors.mutedForeground,
  },
  tipCard: {
    paddingVertical: 12,
  },
  tipRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  tipText: {
    flex: 1,
    fontSize: 15,
    lineHeight: 22,
    color: colors.foreground,
  },
  hint: {
    fontSize: 13,
    lineHeight: 20,
    color: colors.mutedForeground,
  },
});