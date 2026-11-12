/**
 * 设置 Tab：服务器地址（保存 + 测试连接）与宠物管理（列表 / 添加 / 编辑）。
 * 这是骨架的核心屏：网络层与宠物 CRUD 都在这里落地。
 */
import Ionicons from '@expo/vector-icons/Ionicons';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { router } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

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
import { apiFetch } from '@/lib/api';
import { ensureToken, resetToken } from '@/lib/auth';
import { saveDeviceId, useDeviceId } from '@/lib/deviceId';
import { saveServerUrl, useServerUrl } from '@/lib/serverUrl';
import type { Pet } from '@/lib/types';
import { clayPress, colors, radius } from '@/lib/theme';

/** 测试连接状态 */
type TestState = { kind: 'idle' } | { kind: 'testing' } | { kind: 'ok' } | { kind: 'fail' };

export default function SettingsScreen() {
  const serverUrl = useServerUrl();
  const [draft, setDraft] = useState<string | null>(null);
  const [test, setTest] = useState<TestState>({ kind: 'idle' });
  const pets = usePets();

  // 输入框显示草稿（未保存的编辑），没有草稿时显示已保存地址
  const value = draft ?? serverUrl;

  async function handleSave(): Promise<void> {
    await saveServerUrl(value);
    setDraft(null);
    setTest({ kind: 'idle' });
  }

  async function handleTest(): Promise<void> {
    // 测试用当前输入的地址（不必先保存）
    const base = value.trim().replace(/\/+$/, '');
    if (!base) {
      setTest({ kind: 'fail' });
      return;
    }
    setTest({ kind: 'testing' });
    try {
      const res = await fetch(`${base}/healthz`);
      setTest(res.ok ? { kind: 'ok' } : { kind: 'fail' });
    } catch {
      setTest({ kind: 'fail' });
    }
  }

  return (
    <Screen>
      <PageHeader title="设置" subtitle="服务器连接与宠物档案" />

      <Card style={styles.gapColumn}>
        <SectionTitle>服务器</SectionTitle>
        <Field
          label="地址（电脑上 FastAPI 服务的局域网地址）"
          value={value}
          onChangeText={(text) => setDraft(text)}
          placeholder="http://192.168.x.x:8000"
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
        />
        <View style={styles.row}>
          <PrimaryButton
            title="保存"
            onPress={() => void handleSave()}
            style={styles.grow}
          />
          <SecondaryButton title="测试连接" onPress={() => void handleTest()} style={styles.grow} />
        </View>
        <TestStatus state={test} />
      </Card>

      <Card style={styles.gapColumn}>
        <View style={styles.rowBetween}>
          <SectionTitle>宠物管理</SectionTitle>
          <Pressable
            onPress={() => router.push('/pet/new')}
            style={({ pressed }) => [styles.addChip, pressed && clayPress]}
          >
            <Ionicons name="add" size={18} color="#FFFFFF" />
            <Text style={styles.addChipText}>添加</Text>
          </Pressable>
        </View>

        {!serverUrl ? (
          <EmptyState
            icon="server-outline"
            title="还没配置服务器"
            subtitle="先在上方填写地址并保存，宠物档案存在你的电脑上"
          />
        ) : pets.isPending ? (
          <View style={styles.loadingRow}>
            <ActivityIndicator color={colors.primary} />
          </View>
        ) : pets.isError ? (
          <EmptyState
            icon="cloud-offline-outline"
            title="拉取宠物列表失败"
            subtitle={pets.error.message}
          />
        ) : pets.data.items.length === 0 ? (
          <EmptyState
            icon="paw"
            title="还没有宠物"
            subtitle="点右上角「添加」，建立第一只守宫的档案"
          />
        ) : (
          <View style={styles.gapColumn}>
            {pets.data.items.map((pet) => (
              <PetRow key={pet.id} pet={pet} />
            ))}
          </View>
        )}
      </Card>

      <IdentityCard />

      <DeviceCard />
    </Screen>
  );
}

function IdentityCard() {
  const serverUrl = useServerUrl();
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const me = useQuery({
    queryKey: ['me', serverUrl],
    enabled: serverUrl !== '',
    queryFn: () => apiFetch<{ user_id: string }>('/api/v1/users/me'),
    retry: 0,
  });
  const userId = me.data?.user_id ?? null;

  async function handleReset(): Promise<void> {
    setBusy(true);
    try {
      await resetToken();
      if (serverUrl) {
        await ensureToken();
        // 清掉旧账号的缓存，挂载中的查询会自动按新账号重新拉取。
        queryClient.clear();
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card style={styles.gapColumn}>
      <SectionTitle>身份</SectionTitle>
      <Text style={styles.hint}>
        本机使用匿名账号保存数据，不需要注册登录。宠物档案只属于这个账号。
      </Text>
      <Text style={styles.identityLine}>
        {!serverUrl
          ? '未连接服务器'
          : userId
            ? `匿名账号 ${userId.slice(0, 8)}`
            : '正在获取账号…'}
      </Text>
      <Text style={styles.hint}>
        换手机或清除 App 数据后会得到新账号，原来的宠物看不到。
      </Text>
      <SecondaryButton
        title={busy ? '正在重置…' : '重置身份'}
        onPress={() => void handleReset()}
        disabled={!serverUrl || busy}
      />
    </Card>
  );
}

function DeviceCard() {
  const serverUrl = useServerUrl();
  const savedDeviceId = useDeviceId();
  const pets = usePets();
  const [draft, setDraft] = useState<string | null>(null);
  const [boundPetId, setBoundPetId] = useState<string | null>(null);
  const { state, enable, isPending } = useEnablePush();
  const value = draft ?? savedDeviceId;
  const petItems = pets.data?.items ?? [];
  const selectedPetId = boundPetId ?? petItems[0]?.id ?? null;

  async function handleEnable(): Promise<void> {
    if (!value.trim()) return;
    await saveDeviceId(value);
    setDraft(null);
    await enable(value, selectedPetId);
  }

  return (
    <Card style={styles.gapColumn}>
      <SectionTitle>摄像头与提醒</SectionTitle>
      <Text style={styles.hint}>
        填上摄像头的设备编号并绑定一只宠物。设备检测到蜕皮时，会推送提醒到这里。
      </Text>
      <Field
        label="设备编号（device_id）"
        value={value}
        onChangeText={(text) => setDraft(text)}
        placeholder="gecko-eye-01"
        autoCapitalize="none"
        autoCorrect={false}
      />
      <Text style={styles.pickLabel}>绑定宠物</Text>
      {petItems.length === 0 ? (
        <Text style={styles.hint}>先在「宠物管理」里添加一只宠物</Text>
      ) : (
        <View style={styles.chipWrap}>
          {petItems.map((pet) => {
            const active = pet.id === selectedPetId;
            return (
              <Pressable
                key={pet.id}
                onPress={() => setBoundPetId(pet.id)}
                style={[styles.petChip, active && styles.petChipActive]}
              >
                <Text style={[styles.petChipText, active && styles.petChipTextActive]}>
                  {pet.name}
                </Text>
              </Pressable>
            );
          })}
        </View>
      )}
      <PrimaryButton
        title={isPending ? '正在启用…' : '保存并启用通知'}
        onPress={() => void handleEnable()}
        loading={isPending}
        disabled={!serverUrl || !value.trim()}
      />
      <PushStatusText state={state} />
    </Card>
  );
}

function PushStatusText({ state }: { state: ReturnType<typeof useEnablePush>['state'] }) {
  if (state.kind === 'idle') return null;
  if (state.kind === 'working') {
    return <Text style={styles.hint}>正在申请通知权限并注册…</Text>;
  }
  if (state.kind === 'ok') {
    return <Text style={[styles.hint, { color: colors.success }]}>✓ 已启用，检测到蜕皮会推送提醒</Text>;
  }
  const color = state.kind === 'denied' || state.kind === 'error' ? colors.destructive : colors.warning;
  return <Text style={[styles.hint, { color }]}>{state.message}</Text>;
}

function TestStatus({ state }: { state: TestState }) {
  if (state.kind === 'idle') return null;
  if (state.kind === 'testing') {
    return (
      <Text style={styles.testText}>
        <ActivityIndicator size="small" color={colors.mutedForeground} /> 正在测试…
      </Text>
    );
  }
  if (state.kind === 'ok') {
    return (
      <Text style={[styles.testText, { color: colors.success }]}>✓ 连接正常</Text>
    );
  }
  return <Text style={[styles.testText, { color: colors.destructive }]}>✗ 连不上，检查地址与网络</Text>;
}

function PetRow({ pet }: { pet: Pet }) {
  const subtitle = [pet.species, pet.morph].filter(Boolean).join(' · ') || '未填写品种';
  return (
    <Pressable
      onPress={() => router.push(`/pet/${pet.id}`)}
      style={({ pressed }) => [styles.petRow, pressed && clayPress]}
    >
      <View style={styles.petAvatar}>
        <Ionicons name="paw" size={20} color={colors.primary} />
      </View>
      <View style={styles.grow}>
        <Text style={styles.petName}>{pet.name}</Text>
        <Text style={styles.petSub}>{subtitle}</Text>
      </View>
      <Ionicons name="chevron-forward" size={18} color={colors.mutedForeground} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  gapColumn: {
    gap: 12,
  },
  row: {
    flexDirection: 'row',
    gap: 12,
  },
  rowBetween: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  grow: {
    flex: 1,
  },
  testText: {
    fontSize: 13,
    color: colors.mutedForeground,
    fontWeight: '600',
  },
  addChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 2,
    backgroundColor: colors.primary,
    borderRadius: radius.md,
    borderWidth: 2,
    borderColor: colors.primaryDark,
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  addChipText: {
    color: '#FFFFFF',
    fontWeight: '700',
    fontSize: 13,
  },
  loadingRow: {
    paddingVertical: 16,
    alignItems: 'center',
  },
  petRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    backgroundColor: colors.muted,
    borderWidth: 2,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: 12,
  },
  petAvatar: {
    width: 40,
    height: 40,
    borderRadius: radius.md,
    backgroundColor: colors.background,
    borderWidth: 2,
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  petName: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.foreground,
  },
  petSub: {
    fontSize: 12,
    color: colors.mutedForeground,
  },
  hint: {
    fontSize: 13,
    lineHeight: 19,
    color: colors.mutedForeground,
  },
  identityLine: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.foreground,
  },
  pickLabel: {
    fontSize: 13,
    fontWeight: '600',
    color: colors.foreground,
  },
  chipWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  petChip: {
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: radius.md,
    borderWidth: 2,
    borderColor: colors.border,
    backgroundColor: colors.card,
  },
  petChipActive: {
    backgroundColor: colors.primary,
    borderColor: colors.primaryDark,
  },
  petChipText: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.foreground,
  },
  petChipTextActive: {
    color: '#FFFFFF',
  },
});
