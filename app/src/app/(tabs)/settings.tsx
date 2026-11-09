/**
 * 设置 Tab：服务器地址（保存 + 测试连接）与宠物管理（列表 / 添加 / 编辑）。
 * 这是骨架的核心屏：网络层与宠物 CRUD 都在这里落地。
 */
import Ionicons from '@expo/vector-icons/Ionicons';
import { Link } from 'expo-router';
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
import { usePets } from '@/hooks/usePets';
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
          <Link href="/pet/new" asChild>
            <Pressable style={({ pressed }) => [styles.addChip, pressed && clayPress]}>
              <Ionicons name="add" size={18} color="#FFFFFF" />
              <Text style={styles.addChipText}>添加</Text>
            </Pressable>
          </Link>
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
    </Screen>
  );
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
    <Link href={`/pet/${pet.id}`} asChild>
      <Pressable style={({ pressed }) => [styles.petRow, pressed && clayPress]}>
        <View style={styles.petAvatar}>
          <Ionicons name="paw" size={20} color={colors.primary} />
        </View>
        <View style={styles.grow}>
          <Text style={styles.petName}>{pet.name}</Text>
          <Text style={styles.petSub}>{subtitle}</Text>
        </View>
        <Ionicons name="chevron-forward" size={18} color={colors.mutedForeground} />
      </Pressable>
    </Link>
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
});
