/**
 * 萌照相册：把设备这段时间拍到的照片按日期铺开。
 */
import Ionicons from '@expo/vector-icons/Ionicons';
import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';

import { Card, EmptyState, PrimaryButton, Screen } from '@/components/ui';
import { usePets } from '@/hooks/usePets';
import { usePortraitAlbum } from '@/hooks/usePortraits';
import { ensureToken, portraitUrl } from '@/lib/auth';
import { useServerUrl } from '@/lib/serverUrl';
import { clayPress, colors, radius } from '@/lib/theme';

export default function PortraitsScreen() {
  const serverUrl = useServerUrl();
  const petsQuery = usePets();
  const pets = petsQuery.data?.items ?? [];
  const petId = pets[0]?.id ?? null;
  const album = usePortraitAlbum(petId);
  const shots = album.data?.items ?? [];
  const [tokenReady, setTokenReady] = useState(false);

  useEffect(() => {
    void ensureToken()
      .then(() => setTokenReady(true))
      .catch(() => setTokenReady(true));
  }, []);

  if (serverUrl === '') {
    return (
      <Screen>
        <Card>
          <EmptyState icon="cloud-offline" title="App 还没连上电脑" subtitle="先回到「我的」，填好地址。" />
        </Card>
      </Screen>
    );
  }

  if (pets.length === 0) {
    return (
      <Screen>
        <Card style={{ gap: 12 }}>
          <EmptyState icon="paw" title="还没有你的守宫" subtitle="先建个档案，设备才会开始拍" />
          <PrimaryButton title="创建档案" onPress={() => router.push('/pet/new')} />
        </Card>
      </Screen>
    );
  }

  if (shots.length === 0) {
    return (
      <Screen>
        <Text style={styles.subtitle}>设备每天会挑一张最好的留下来</Text>
        <Card>
          <EmptyState
            icon="images"
            title="还没有照片"
            subtitle="设备拍够几张后，这里就会出现。也可以在「萌照设置」里改成每天多拍几张。"
          />
        </Card>
        <PrimaryButton
          title="去改萌照设置"
          onPress={() => router.push('/portrait-settings')}
        />
      </Screen>
    );
  }

  return (
    <Screen>
      <Text style={styles.subtitle}>已经攒了 {shots.length} 张</Text>
      <View style={styles.grid}>
        {shots.map((shot) => (
          <Pressable
            key={shot.id}
            onPress={() => router.push({ pathname: '/portrait/[id]', params: { id: shot.id, local_date: shot.local_date } })}
            accessibilityRole="button"
            accessibilityLabel={`${shot.local_date} 的萌照`}
            style={({ pressed }) => [styles.cell, pressed && clayPress]}
          >
            {tokenReady ? (
              <Image source={{ uri: portraitUrl(shot.id) }} style={styles.image} />
            ) : (
              <View style={styles.imagePlaceholder} />
            )}
            <Text style={styles.caption}>
              {shot.local_date.slice(5, 7)}月{shot.local_date.slice(8)}日
            </Text>
          </Pressable>
        ))}
      </View>
      <Card style={styles.tip}>
        <View style={styles.tipRow}>
          <Ionicons name="camera-outline" size={18} color={colors.primaryDark} />
          <Text style={styles.tipText}>
            想要更好的照片？把摄像头放近一点，拍之前擦一下玻璃。
          </Text>
        </View>
      </Card>
    </Screen>
  );
}

const styles = StyleSheet.create({
  subtitle: {
    fontSize: 14,
    color: colors.mutedForeground,
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  cell: {
    width: '31%',
    gap: 4,
  },
  image: {
    width: '100%',
    aspectRatio: 1,
    borderRadius: radius.md,
    borderWidth: 2,
    borderColor: colors.border,
    backgroundColor: colors.card,
  },
  caption: {
    fontSize: 12,
    color: colors.mutedForeground,
    textAlign: 'center',
  },
  imagePlaceholder: {
    width: '100%',
    aspectRatio: 1,
    borderRadius: radius.md,
    borderWidth: 2,
    borderColor: colors.border,
    backgroundColor: colors.background,
  },
  tip: {
    paddingVertical: 12,
  },
  tipRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  tipText: {
    flex: 1,
    fontSize: 13,
    lineHeight: 20,
    color: colors.foreground,
  },
});
