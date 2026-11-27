/**
 * 「我的」：守宫档案、提醒绑定、功能入口、以及折叠起来的高级设置。
 * 纸感极简（P34）：所有入口用 1px 纸线分隔的列表，不套卡片框；分组靠 Eyebrow 与留白。
 *
 * P37（2026-11-27）层级重排：一屏只有一个最强标题（PageHeader 的 display），
 * 其余全部收进 Group（组间 40、组内 12）；每个设置行只留「body 主标签 + Hint 辅助」两级，
 * 长说明压成一行 Note，采集器编号移进高级设置折叠区。
 */
import Ionicons from '@expo/vector-icons/Ionicons';
import { useQueryClient } from '@tanstack/react-query';
import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import {
  BrandBar,
  EmptyState,
  Field,
  Group,
  Hint,
  ListRow,
  Note,
  PageHeader,
  PrimaryButton,
  Screen,
  SecondaryButton,
} from '@/components/ui';
import { useEnablePush } from '@/hooks/useAlerts';
import { usePets } from '@/hooks/usePets';
import { ensureToken, resetToken } from '@/lib/auth';
import { saveDeviceId, useDeviceId } from '@/lib/deviceId';
import { saveServerUrl, useServerUrl } from '@/lib/serverUrl';
import { clayPress, colors, hairline, space, type } from '@/lib/theme';
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
    if (state.kind === 'unsupported')
      return '这台设备暂时收不到系统通知，提醒会显示在「蜕皮记录」里。';
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
      <BrandBar />
      <PageHeader title="我的" subtitle="你的守宫、提醒和设置" />

      <Group title="我的守宫">
        {petsQuery.isLoading ? (
          <Hint>加载中…</Hint>
        ) : pets.length === 0 ? (
          <EmptyState title="还没有档案" subtitle="点下面「添加一只守宫」，10 秒就能建好" />
        ) : (
          <View>
            {pets.map((pet, index) => (
              <Pressable
                key={pet.id}
                onPress={() => router.push({ pathname: '/pet/[id]', params: { id: pet.id } })}
                accessibilityRole="button"
                style={({ pressed }) => [
                  styles.petRow,
                  index < pets.length - 1 && styles.rowDivider,
                  pressed && clayPress,
                ]}
              >
                <View style={styles.petText}>
                  <Text style={styles.petName}>{pet.name}</Text>
                  <Hint>
                    {pet.species ?? '豹纹守宫'}
                    {pet.morph ? ` · ${pet.morph}` : ''}
                  </Hint>
                </View>
                <Ionicons name="chevron-forward" size={17} color={colors.ghostForeground} />
              </Pressable>
            ))}
          </View>
        )}

        <ListRow title="添加一只守宫" onPress={() => router.push('/pet/new')} last />
      </Group>

      <Group title="蜕皮提醒">
        <Note>接上摄像头之后，它白天会定时拍一张，看到蜕皮的白皮就提醒你。</Note>
        <PrimaryButton
          title="保存并开启通知"
          onPress={() => void handleEnable()}
          loading={isPending}
        />
        {pushStatusText() !== '' ? <Hint>{pushStatusText()}</Hint> : null}
      </Group>

      <Group title="功能">
        <View>
          <ListRow
            title="接上家里的摄像头"
            hint="接一次，之后自动拍"
            onPress={() => router.push('/cameras')}
          />
          <ListRow
            title="萌照相册"
            hint="每天挑一张它的样子"
            onPress={() => router.push('/portraits')}
          />
          <ListRow
            title="萌照设置"
            hint="每天拍几张、什么时段拍"
            onPress={() => router.push('/portrait-settings')}
          />
          <ListRow
            title="分享照片，帮到别的守宫"
            hint="默认关闭，随时可以停"
            onPress={() => router.push('/contribution')}
          />
          <ListRow
            title="蜕皮知识"
            hint="为什么白、要不要帮它撕"
            onPress={() => router.push('/knowledge')}
          />
          <ListRow
            title="蜕皮不顺利？做个检查"
            hint="六道题，看要不要找医生"
            onPress={() => router.push('/risk')}
            last
          />
        </View>
      </Group>

      <Group>
        <Pressable
          onPress={() => setAdvancedOpen((v) => !v)}
          accessibilityRole="button"
          style={styles.advancedToggle}
        >
          <Text style={styles.advancedText}>
            {advancedOpen ? '收起高级设置' : '高级设置'}
          </Text>
          <Ionicons
            name={advancedOpen ? 'chevron-up' : 'chevron-down'}
            size={13}
            color={colors.faintForeground}
          />
        </Pressable>

        {advancedOpen ? (
          <View style={styles.advancedBlock}>
            <Field
              label="采集器编号（只有用 ESP32 采集器时才需要）"
              placeholder="留空就行"
              autoCapitalize="none"
              autoCorrect={false}
              value={deviceValue}
              onChangeText={setDeviceDraft}
            />
            <Hint>
              只有自己搭服务端的人才需要改这里。地址格式像 http://192.168.1.10:8000
            </Hint>
            <Field
              label="服务端地址"
              placeholder={serverUrl === '' ? '还没填' : serverUrl}
              autoCapitalize="none"
              autoCorrect={false}
              value={addressDraft}
              onChangeText={setAddressDraft}
            />
            <PrimaryButton title="保存地址" onPress={() => void handleSaveAddress()} />
            <SecondaryButton
              title="重置身份（会看不到原来的档案）"
              onPress={() => void handleReset()}
            />
            {savedHint ? <Hint>{savedHint}</Hint> : null}
          </View>
        ) : null}
      </Group>

      <Hint style={styles.about}>守宫蜕皮小助手 · 0.1.0</Hint>
    </Screen>
  );
}

const styles = StyleSheet.create({
  petRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.lg,
    minHeight: 56,
  },
  rowDivider: {
    borderBottomWidth: hairline,
    borderBottomColor: colors.divider,
  },
  petText: {
    flex: 1,
    gap: space.xxs,
  },
  petName: {
    ...type.body,
    fontWeight: '600',
    color: colors.foreground,
  },
  advancedToggle: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: space.xs,
    paddingVertical: space.md,
    minHeight: 44,
  },
  advancedText: {
    ...type.body,
    fontWeight: '600',
    color: colors.faintForeground,
  },
  advancedBlock: {
    gap: space.tight,
  },
  about: {
    textAlign: 'center',
    marginTop: space.group,
  },
});
