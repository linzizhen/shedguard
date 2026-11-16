/**
 * 摄像头列表：接上家里已有的摄像头，定时抓拍交给服务端判定。
 */
import { router } from 'expo-router';
import { Alert, Pressable, StyleSheet, Text, View } from 'react-native';

import { Card, EmptyState, PrimaryButton, Screen, SecondaryButton } from '@/components/ui';
import {
  useCameraSnapshot,
  useCameras,
  useDeleteCamera,
  useTestCamera,
} from '@/hooks/useCameras';
import type { CameraItem, CameraStatus } from '@/lib/types';
import { useServerUrl } from '@/lib/serverUrl';
import { clayPress, colors, radius } from '@/lib/theme';

const STATUS_META: Record<CameraStatus, { label: string; color: string; hint: string }> = {
  never_tested: { label: '还没试过', color: colors.mutedForeground, hint: '点一下「试试连得上」' },
  ok: { label: '正常', color: colors.success, hint: '能取到画面' },
  auth_failed: { label: '账号不对', color: colors.destructive, hint: '检查用户名密码或应用密钥' },
  unreachable: { label: '连不上', color: colors.warning, hint: '检查地址、电源和网络' },
};

function formatMoment(raw: string | null): string {
  if (!raw) {
    return '还没拍过';
  }
  return raw.slice(0, 10);
}

function CameraCard({ camera }: { camera: CameraItem }) {
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
      onSuccess: () => Alert.alert('拍好了', '这张照片已经交给电脑去判定了。'),
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
    <Card style={styles.card}>
      <View style={styles.headRow}>
        <View style={[styles.dot, { backgroundColor: meta.color }]} />
        <Text style={styles.label}>{camera.label}</Text>
        <Text style={[styles.status, { color: meta.color }]}>{meta.label}</Text>
      </View>
      <Text style={styles.hint}>
        {camera.last_error.trim() === '' ? meta.hint : camera.last_error}
      </Text>
      <Text style={styles.moment}>最近一张：{formatMoment(camera.last_frame_at_utc)}</Text>
      <View style={styles.actions}>
        <Pressable
          onPress={onTest}
          disabled={test.isPending}
          accessibilityRole="button"
          accessibilityLabel={`测试 ${camera.label} 能不能连上`}
          style={({ pressed }) => [styles.action, pressed && clayPress]}
        >
          <Text style={styles.actionText}>
            {test.isPending ? '正在试…' : '试试连得上'}
          </Text>
        </Pressable>
        <Pressable
          onPress={onSnapshot}
          disabled={snapshot.isPending}
          accessibilityRole="button"
          accessibilityLabel={`让 ${camera.label} 现在拍一张`}
          style={({ pressed }) => [styles.action, pressed && clayPress]}
        >
          <Text style={styles.actionText}>
            {snapshot.isPending ? '正在拍…' : '现在拍一张'}
          </Text>
        </Pressable>
        <Pressable
          onPress={onDelete}
          accessibilityRole="button"
          accessibilityLabel={`删除摄像头 ${camera.label}`}
          style={({ pressed }) => [styles.action, pressed && clayPress]}
        >
          <Text style={[styles.actionText, styles.danger]}>删掉</Text>
        </Pressable>
      </View>
    </Card>
  );
}

export default function CamerasScreen() {
  const serverUrl = useServerUrl();
  const cameras = useCameras();
  const items = cameras.data?.items ?? [];

  if (serverUrl === '') {
    return (
      <Screen>
        <Card>
          <EmptyState
            icon="cloud-offline"
            title="App 还没连上电脑"
            subtitle="先回到「我的」，填好地址。"
          />
        </Card>
      </Screen>
    );
  }

  return (
    <Screen>
      <Text style={styles.subtitle}>
        接上家里已有的摄像头，白天每隔一段时间抓一张，交给电脑判断它是不是在蜕皮。
      </Text>

      {cameras.isPending ? <Text style={styles.subtitle}>正在加载…</Text> : null}
      {cameras.isError ? (
        <Card>
          <EmptyState icon="alert-circle" title="没加载出来" subtitle={cameras.error.message} />
        </Card>
      ) : null}

      {items.length === 0 && !cameras.isPending && !cameras.isError ? (
        <Card>
          <EmptyState
            icon="videocam"
            title="还没有接摄像头"
            subtitle="支持萤石云，也支持能给出 RTSP 地址的网络摄像头。"
          />
        </Card>
      ) : null}

      {items.map((camera) => (
        <CameraCard key={camera.id} camera={camera} />
      ))}

      <PrimaryButton title="接一个摄像头" onPress={() => router.push('/camera-new')} />
      <SecondaryButton title="怎么找摄像头的地址" onPress={() => router.push('/knowledge')} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  subtitle: {
    fontSize: 14,
    lineHeight: 21,
    color: colors.mutedForeground,
  },
  card: {
    gap: 6,
  },
  headRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  dot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  label: {
    flex: 1,
    fontSize: 16,
    fontWeight: '700',
    color: colors.foreground,
  },
  status: {
    fontSize: 13,
    fontWeight: '700',
  },
  hint: {
    fontSize: 13,
    lineHeight: 20,
    color: colors.foreground,
  },
  moment: {
    fontSize: 12,
    color: colors.mutedForeground,
  },
  actions: {
    flexDirection: 'row',
    gap: 12,
    marginTop: 4,
  },
  action: {
    minHeight: 44,
    justifyContent: 'center',
  },
  actionText: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.primaryDark,
  },
  danger: {
    color: colors.destructive,
  },
  empty: {
    borderRadius: radius.md,
  },
});