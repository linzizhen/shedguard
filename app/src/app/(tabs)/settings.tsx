/**
 * 「我的」：守宫档案、提醒绑定、知识入口、以及折叠起来的高级设置。
 * 高级设置里才有服务器地址——普通用户不需要看。
 */
import Ionicons from '@expo/vector-icons/Ionicons';
import { useQueryClient } from '@tanstack/react-query';
import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import {
  Card,
  EmptyState,
  Field,
  PageHeader,
  PrimaryButton,
  Screen,
  SecondaryButton,
  SectionTitle,
} from '@/components/ui';
import { useEnablePush } from '@/hooks/useAlerts';
import { usePets } from '@/hooks/usePets';
import { ensureToken, resetToken } from '@/lib/auth';
import { saveDeviceId, useDeviceId } from '@/lib/deviceId';
import { saveServerUrl, useServerUrl } from '@/lib/serverUrl';
import { colors, radius } from '@/lib/theme';
import type { Pet } from '@/lib/types';

export default function ProfileScreen() {
  const serverUrl = useServerUrl();
  const deviceId = useDeviceId();
  const petsQuery = usePets();
  const queryClient = useQueryClient();
  const { state, enable, isPending } = useEnablePush();

  const [deviceDraft, setDeviceDraft] = useState('');
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [addressDraft, setAddressDraft] = useState('');
  const [savedHint, setSavedHint] = useState<string | null>(null);

  // 没手动改过时显示已保存的设备号；一旦开始输入就以输入框为准
  const deviceValue = deviceDraft === '' ? deviceId : deviceDraft;

  const pets: Pet[] = petsQuery.data?.items ?? [];

  function pushStatusText(): string {
    if (state.kind === 'ok') return '通知已开启，发现蜕皮会直接弹到手机上。';
    if (state.kind === 'bound') return state.message;
    if (state.kind === 'denied') return '系统通知被拒绝了，提醒会显示在「蜕皮记录」里。';
    if (state.kind === 'unsupported') return '这台设备暂时收不到系统通知，提醒会显示在「蜕皮记录」里。';
    if (state.kind === 'working') return '正在开启…';
    if (state.kind === 'error') return '没开启成功，稍后再试。';
    return '';
  }

  async function handleEnable() {
    const id = deviceDraft.trim() || deviceId || 'gecko-eye-01';
    await saveDeviceId(id);
    await enable(id, pets[0]?.id ?? null);
  }

  async function handleSaveAddress() {
    const value = addressDraft.trim();
    if (value === '') return;
    await saveServerUrl(value);
    setSavedHint('地址已保存');
    void queryClient.invalidateQueries();
  }

  async function handleReset() {
    await resetToken();
    try {
      await ensureToken();
    } catch {
      // 服务器不通时静默，下一次请求会再试
    }
    queryClient.clear();
    setSavedHint('已换了一个新身份，原来的档案看不到了');
  }

  return (
    <Screen>
      <PageHeader title="我的" subtitle="你的守宫、提醒和设置" />

      <Card style={{ gap: 14 }}>
        <View style={styles.rowBetween}>
          <SectionTitle>我的守宫</SectionTitle>
          <Pressable onPress={() => router.push('/pet/new')} accessibilityRole="button" style={styles.addChip}>
            <Text style={styles.addChipText}>添加</Text>
          </Pressable>
        </View>

        {petsQuery.isLoading ? (
          <Text style={styles.muted}>加载中…</Text>
        ) : pets.length === 0 ? (
          <EmptyState icon="paw" title="还没有档案" subtitle="点右上角「添加」给守宫建个档案" />
        ) : (
          <View style={{ gap: 10 }}>
            {pets.map((pet) => (
              <Pressable
                key={pet.id}
                onPress={() => router.push({ pathname: '/pet/[id]', params: { id: pet.id } })}
                accessibilityRole="button"
                style={({ pressed }) => [styles.petRow, pressed && styles.pressed]}
              >
                <View style={styles.petIcon}>
                  <Ionicons name="paw" size={18} color={colors.primaryDark} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.petName}>{pet.name}</Text>
                  <Text style={styles.petMeta}>{pet.species ?? '豹纹守宫'}</Text>
                </View>
                <Ionicons name="chevron-forward" size={18} color={colors.mutedForeground} />
              </Pressable>
            ))}
          </View>
        )}
      </Card>

      <Card style={{ gap: 12 }}>
        <SectionTitle>蜕皮提醒</SectionTitle>
        <Text style={styles.body}>
          接上摄像头之后，它每 30 分钟拍一张。发现守宫身上有蜕皮的白皮，就会提醒你。
        </Text>
        <Field
          label="摄像头编号"
          placeholder="gecko-eye-01"
          autoCapitalize="none"
          autoCorrect={false}
          value={deviceValue}
          onChangeText={setDeviceDraft}
        />
        <PrimaryButton
          title="保存并开启通知"
          onPress={() => void handleEnable()}
          loading={isPending}
        />
        {pushStatusText() !== '' ? <Text style={styles.hint}>{pushStatusText()}</Text> : null}
      </Card>

      <Pressable
        onPress={() => router.push('/knowledge')}
        accessibilityRole="button"
        style={({ pressed }) => [styles.linkRow, pressed && styles.pressed]}
      >
        <Ionicons name="book-outline" size={20} color={colors.primaryDark} />
        <Text style={styles.linkText}>蜕皮知识</Text>
        <Ionicons name="chevron-forward" size={18} color={colors.mutedForeground} />
      </Pressable>

      <Pressable
        onPress={() => router.push('/risk')}
        accessibilityRole="button"
        style={({ pressed }) => [styles.linkRow, pressed && styles.pressed]}
      >
        <Ionicons name="medkit-outline" size={20} color={colors.primaryDark} />
        <Text style={styles.linkText}>蜕皮不顺利？做个检查</Text>
        <Ionicons name="chevron-forward" size={18} color={colors.mutedForeground} />
      </Pressable>

      <Pressable
        onPress={() => setAdvancedOpen((v) => !v)}
        accessibilityRole="button"
        style={styles.advancedToggle}
      >
        <Text style={styles.advancedText}>
          {advancedOpen ? '收起高级设置' : '高级设置'}
        </Text>
      </Pressable>

      {advancedOpen ? (
        <Card style={{ gap: 12 }}>
          <Text style={styles.hint}>
            只有自己搭服务器的人才需要改这里。地址格式像 http://192.168.1.10:8000
          </Text>
          <Field
            label="电脑上那个程序的地址"
            placeholder={serverUrl === '' ? '还没填' : serverUrl}
            autoCapitalize="none"
            autoCorrect={false}
            value={addressDraft}
            onChangeText={setAddressDraft}
          />
          <PrimaryButton title="保存地址" onPress={() => void handleSaveAddress()} />
          <SecondaryButton title="重置身份（会看不到原来的档案）" onPress={() => void handleReset()} />
          {savedHint ? <Text style={styles.hint}>{savedHint}</Text> : null}
        </Card>
      ) : null}

      <Text style={styles.about}>守宫蜕皮小助手 · 0.1.0</Text>
    </Screen>
  );
}

const styles = StyleSheet.create({
  rowBetween: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  addChip: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    minHeight: 40,
    justifyContent: 'center',
    borderRadius: radius.md,
    backgroundColor: colors.primary,
  },
  addChipText: {
    color: '#FFFFFF',
    fontSize: 13,
    fontWeight: '800',
  },
  muted: {
    fontSize: 14,
    color: colors.mutedForeground,
  },
  body: {
    fontSize: 15,
    lineHeight: 22,
    color: colors.foreground,
  },
  petRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingVertical: 10,
    paddingHorizontal: 10,
    borderRadius: radius.md,
    borderWidth: 2,
    borderColor: colors.border,
    backgroundColor: colors.background,
    minHeight: 56,
  },
  pressed: {
    opacity: 0.85,
  },
  petIcon: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.card,
    alignItems: 'center',
    justifyContent: 'center',
  },
  petName: {
    fontSize: 16,
    fontWeight: '800',
    color: colors.foreground,
  },
  petMeta: {
    fontSize: 13,
    color: colors.mutedForeground,
  },
  hint: {
    fontSize: 13,
    lineHeight: 19,
    color: colors.mutedForeground,
  },
  linkRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    backgroundColor: colors.card,
    borderRadius: radius.lg,
    borderWidth: 3,
    borderColor: colors.border,
    paddingHorizontal: 16,
    paddingVertical: 16,
    minHeight: 56,
  },
  linkText: {
    flex: 1,
    fontSize: 16,
    fontWeight: '700',
    color: colors.foreground,
  },
  advancedToggle: {
    paddingVertical: 12,
    minHeight: 44,
    justifyContent: 'center',
    alignItems: 'center',
  },
  advancedText: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.mutedForeground,
    textDecorationLine: 'underline',
  },
  about: {
    fontSize: 12,
    color: colors.mutedForeground,
    textAlign: 'center',
    marginTop: 8,
  },
});
