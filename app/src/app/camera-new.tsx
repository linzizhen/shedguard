/**
 * 接一个摄像头：填名字和地址，保存后立刻试一次能不能连上。
 * 纸感极简（P34）：分段用 Eyebrow + 1px 纸线，输入用下划线，不再套卡片框。
 */
import { router } from 'expo-router';
import { useState } from 'react';
import { Alert, Pressable, StyleSheet, Text, View } from 'react-native';

import { Divider, Eyebrow, Field, PrimaryButton, Screen } from '@/components/ui';
import { useCreateCamera, useTestCamera } from '@/hooks/useCameras';
import type { CameraProvider } from '@/lib/types';
import { clayPress, colors, hairline, radius, space, type } from '@/lib/theme';

const PROVIDERS: { key: CameraProvider; label: string; hint: string }[] = [
  { key: 'rtsp', label: '网络摄像头', hint: '能给出一条 rtsp:// 地址' },
  { key: 'ezviz', label: '萤石云', hint: '有一台萤石摄像头' },
];

export default function CameraNewScreen() {
  const [provider, setProvider] = useState<CameraProvider>('rtsp');
  const [label, setLabel] = useState('');
  const [url, setUrl] = useState('');
  const [user, setUser] = useState('');
  const [credential, setCredential] = useState('');
  const [serial, setSerial] = useState('');
  const [appKey, setAppKey] = useState('');
  const [appSecret, setAppSecret] = useState('');

  const create = useCreateCamera();
  const test = useTestCamera();

  const missing =
    label.trim() === '' ||
    (provider === 'rtsp'
      ? url.trim() === ''
      : serial.trim() === '' || appKey.trim() === '' || appSecret.trim() === '');
  const busy = create.isPending || test.isPending;

  const onSave = () => {
    if (missing) {
      Alert.alert(
        '还差一点',
        provider === 'rtsp' ? '名字和地址都要填。' : '名字、序列号和应用密钥都要填。',
      );
      return;
    }
    const config: Record<string, string> =
      provider === 'rtsp'
        ? {
            url: url.trim(),
            ...(user.trim() === '' ? {} : { user: user.trim() }),
            ...(credential === '' ? {} : { credential }),
          }
        : {
            device_serial: serial.trim(),
            app_key: appKey.trim(),
            app_secret: appSecret.trim(),
            channel: '1',
          };

    create.mutate(
      { provider, label: label.trim(), config },
      {
        onSuccess: (camera) => {
          test.mutate(camera.id, {
            onSuccess: (result) => {
              Alert.alert(
                result.ok ? '接上了' : '存下来了，但没连上',
                result.ok ? '这台摄像头可以用了。' : result.detail,
                [{ text: '好', onPress: () => router.back() }],
              );
            },
            onError: (error: Error) => {
              Alert.alert('存下来了', `一会儿可以在列表里再试一次。${error.message}`, [
                { text: '好', onPress: () => router.back() },
              ]);
            },
          });
        },
        onError: (error: Error) => Alert.alert('没存上', error.message),
      },
    );
  };

  return (
    <Screen>
      <Text style={styles.subtitle}>
        摄像头留在家里的箱子上方，服务端会定时来取一张图。我们不会控制它，只是看。
      </Text>

      <Divider />

      <Eyebrow>用哪一种</Eyebrow>
      <View style={styles.providerRow}>
        {PROVIDERS.map((item) => {
          const active = item.key === provider;
          return (
            <Pressable
              key={item.key}
              onPress={() => setProvider(item.key)}
              accessibilityRole="button"
              accessibilityState={{ selected: active }}
              accessibilityLabel={`选择${item.label}`}
              style={({ pressed }) => [
                styles.provider,
                active && styles.providerActive,
                pressed && clayPress,
              ]}
            >
              <Text style={[styles.providerLabel, active && styles.providerLabelActive]}>
                {item.label}
              </Text>
              <Text style={styles.providerHint}>{item.hint}</Text>
            </Pressable>
          );
        })}
      </View>

      <Field
        label="给它起个名字"
        value={label}
        onChangeText={setLabel}
        placeholder="比如：小橘子的箱子"
        maxLength={64}
      />
      {provider === 'rtsp' ? (
        <>
          <Field
            label="摄像头地址"
            value={url}
            onChangeText={setUrl}
            placeholder="rtsp://192.168.1.9:554/stream"
            autoCapitalize="none"
            autoCorrect={false}
          />
          <Field
            label="用户名（如果摄像头有）"
            value={user}
            onChangeText={setUser}
            placeholder="admin"
            autoCapitalize="none"
            autoCorrect={false}
          />
          <Field
            label="密码（如果摄像头有）"
            value={credential}
            onChangeText={setCredential}
            placeholder="密码会加密保存"
            secureTextEntry
            autoCapitalize="none"
          />
        </>
      ) : (
        <>
          <Field
            label="设备序列号"
            value={serial}
            onChangeText={setSerial}
            placeholder="萤石 App 里能看到"
            autoCapitalize="none"
            autoCorrect={false}
          />
          <Field
            label="应用 Key"
            value={appKey}
            onChangeText={setAppKey}
            placeholder="开放平台里应用的 key"
            autoCapitalize="none"
            autoCorrect={false}
          />
          <Field
            label="应用密钥"
            value={appSecret}
            onChangeText={setAppSecret}
            placeholder="会加密保存"
            secureTextEntry
            autoCapitalize="none"
          />
        </>
      )}

      <Divider />

      <PrimaryButton
        title={busy ? '正在试…' : '保存并试一下'}
        onPress={onSave}
        disabled={busy}
      />
      <Text style={styles.note}>
        密码只保存在你自己的电脑上，接口不会把它回传回来。想换摄像头随时可以删掉。
      </Text>
    </Screen>
  );
}

const styles = StyleSheet.create({
  subtitle: {
    ...type.bodySm,
    color: colors.mutedForeground,
  },
  providerRow: {
    flexDirection: 'row',
    gap: space.sm,
  },
  provider: {
    flex: 1,
    gap: 3,
    paddingVertical: space.md,
    paddingHorizontal: space.md,
    borderRadius: radius.lg,
    borderWidth: hairline,
    borderColor: colors.border,
  },
  providerActive: {
    borderColor: colors.foreground,
    backgroundColor: colors.muted,
  },
  providerLabel: {
    ...type.bodySm,
    fontWeight: '700',
    color: colors.foreground,
  },
  providerLabelActive: {
    color: colors.foreground,
  },
  providerHint: {
    ...type.caption,
    fontSize: 12,
    color: colors.mutedForeground,
  },
  note: {
    ...type.caption,
    color: colors.faintForeground,
  },
});
