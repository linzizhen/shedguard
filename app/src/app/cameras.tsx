/**
 * 摄像头列表：接上家里已有的摄像头，定时抓拍交给服务端判定。
 * 纸感极简（P34）：每台摄像头是一条 1px 纸线分隔的记录，不套卡片框。
 */
import { router } from 'expo-router';
import { Alert, Pressable, StyleSheet, Text, View } from 'react-native';

import { Badge, Divider, EmptyState, Marker, PrimaryButton, Screen } from '@/components/ui';
import {
  useCameraSnapshot,
  useCameras,
  useDeleteCamera,
  useTestCamera,
} from '@/hooks/useCameras';
import { useServerUrl } from '@/lib/serverUrl';
import { clayPress, colors, hairline, radius, space, type } from '@/lib/theme';
import type { CameraItem, CameraStatus } from '@/lib/types';

const STATUS_META: Record<
  CameraStatus,
  { label: string; tone: 'neutral' | 'success' | 'warning' | 'danger'; hint: string }
> = {
  never_tested: { label: '还没试过', tone: 'neutral', hint: '点一下「试试连得上」' },
  ok: { label: '正常', tone: 'success', hint: '能取到画面' },
  auth_failed: { label: '账号不对', tone: 'danger', hint: '检查用户名密码或应用密钥' },
  unreachable: { label: '连不上', tone: 'warning', hint: '检查地址、电源和网络' },
};

function formatMoment(raw: string | null): string {
  if (!raw) {
    return '还没拍过';
  }
  return raw.slice(0, 10);
}

function CameraRow({ camera, last }: { camera: CameraItem; last: boolean }) {
  const test = useTestCamera();
  const snapshot = useCameraSnapshot();
  const remove = useDeleteCamera();
  const meta = STATUS_META[camera.status];

  const onTest = () => {
    test.mutate(camera.id, {
      onSuccess: (result) => {
        Alert.alert(result.ok ? '连得上' : '没连上', result.detail);
      },
      onError: (error: Error) => Alert.alert('没试成', error.message),
    });
  };

  const onSnapshot = () => {
    snapshot.mutate(camera.id, {
      onSuccess: () => Alert.alert('拍好了', '这张照片已经交给服务端去判定了。'),
      onError: (error: Error) => Alert.alert('没拍成', error.message),
    });
  };

  const onDelete = () => {
    Alert.alert('删掉这个摄像头？', '只是从这里移除，不会动你的摄像头本身。', [
      { text: '先留着', style: 'cancel' },
      {
        text: '删掉',
        style: 'destructive',
        onPress: () =>
          remove.mutate(camera.id, {
            onError: (error: Error) => Alert.alert('没删掉', error.message),
          }),
      },
    ]);
  };

  return (
    <View style={[styles.row, !last && styles.rowDivider]}>
      <View style={styles.headRow}>
        <View style={styles.headText}>
          <Text style={styles.label}>{camera.label}</Text>
          <Text style={styles.moment}>最近一张：{formatMoment(camera.last_frame_at_utc)}</Text>
        </View>
        <Badge label={meta.label} tone={meta.tone} />
      </View>

      <Text style={styles.hint}>
        {camera.last_error.trim() === '' ? meta.hint : camera.last_error}
      </Text>

      <View style={styles.actions}>
        <Pressable
          onPress={onTest}
          disabled={test.isPending}
          accessibilityRole="button"
          accessibilityLabel={`测试 ${camera.label} 能不能连上`}
          style={({ pressed }) => [styles.action, pressed && clayPress]}
        >
          <Text style={styles.actionText}>{test.isPending ? '正在试…' : '试试连得上'}</Text>
        </Pressable>
        <Pressable
          onPress={onSnapshot}
          disabled={snapshot.isPending}
          accessibilityRole="button"
          accessibilityLabel={`让 ${camera.label} 现在拍一张`}
          style={({ pressed }) => [styles.action, pressed && clayPress]}
        >
          <Text style={styles.actionText}>{snapshot.isPending ? '正在拍…' : '现在拍一张'}</Text>
        </Pressable>
        <Pressable
          onPress={onDelete}
          accessibilityRole="button"
          accessibilityLabel={`删除摄像头 ${camera.label}`}
          style={({ pressed }) => [styles.actionGhost, pressed && clayPress]}
        >
          <Text style={styles.actionGhostText}>删掉</Text>
        </Pressable>
      </View>
    </View>
  );
}

export default function CamerasScreen() {
  const serverUrl = useServerUrl();
  const cameras = useCameras();
  const items = cameras.data?.items ?? [];

  if (serverUrl === '') {
    return (
      <Screen>
        <EmptyState title="还没连上服务端" subtitle="先回到「我的」，填好地址。" />
      </Screen>
    );
  }

  return (
    <Screen>
      <Text style={styles.subtitle}>
        接上家里已有的摄像头，白天每隔一段时间抓一张，交给服务端判断它是不是在蜕皮。
      </Text>

      <Divider />

      {cameras.isPending ? <Text style={styles.subtitle}>正在加载…</Text> : null}
      {cameras.isError ? (
        <EmptyState title="没加载出来" subtitle={cameras.error.message} />
      ) : null}

      {items.length === 0 && !cameras.isPending && !cameras.isError ? (
        <EmptyState
          title="还没有接摄像头"
          subtitle="支持萤石云，也支持能给出 RTSP 地址的网络摄像头。"
        />
      ) : null}

      {items.map((camera, index) => (
        <CameraRow key={camera.id} camera={camera} last={index === items.length - 1} />
      ))}

      {items.length > 0 ? <Divider /> : null}

      <PrimaryButton title="接一个摄像头" onPress={() => router.push('/camera-new')} />

      {items.length === 0 ? (
        <View style={styles.note}>
          <Marker />
          <Text style={styles.noteText}>
            没有摄像头也能用：直接在首页拍照，效果一样。
          </Text>
        </View>
      ) : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  subtitle: {
    ...type.bodySm,
    color: colors.mutedForeground,
  },
  row: {
    paddingVertical: space.lg,
    gap: space.sm,
  },
  rowDivider: {
    borderBottomWidth: hairline,
    borderBottomColor: colors.divider,
  },
  headRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
  },
  headText: {
    flex: 1,
    gap: 2,
  },
  label: {
    ...type.heading,
    fontSize: 16,
    color: colors.foreground,
  },
  moment: {
    ...type.caption,
    fontSize: 12,
    color: colors.mutedForeground,
  },
  hint: {
    ...type.bodySm,
    color: colors.body,
  },
  actions: {
    flexDirection: 'row',
    gap: space.sm,
    flexWrap: 'wrap',
    marginTop: space.xs,
  },
  action: {
    minHeight: 36,
    justifyContent: 'center',
    paddingHorizontal: space.md,
    borderRadius: radius.pill,
    backgroundColor: colors.foreground,
  },
  actionText: {
    ...type.caption,
    fontWeight: '700',
    color: colors.onPrimary,
  },
  actionGhost: {
    minHeight: 36,
    justifyContent: 'center',
    paddingHorizontal: space.md,
    borderRadius: radius.pill,
    borderWidth: hairline,
    borderColor: colors.border,
  },
  actionGhostText: {
    ...type.caption,
    fontWeight: '600',
    color: colors.mutedForeground,
  },
  note: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
  },
  noteText: {
    ...type.caption,
    flex: 1,
    color: colors.faintForeground,
  },
});
