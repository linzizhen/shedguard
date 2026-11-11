/**
 * 知识 Tab：六个话题卡片列表，点击进入详情。
 * 后端：GET /api/v1/knowledge/topics。
 */
import { router } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { Card, EmptyState, PageHeader, Screen } from '@/components/ui';
import { useKnowledgeTopics } from '@/hooks/useKnowledge';
import { useServerUrl } from '@/lib/serverUrl';
import { colors, radius } from '@/lib/theme';

export default function KnowledgeScreen() {
  const serverUrl = useServerUrl();
  const topicsQuery = useKnowledgeTopics();

  return (
    <Screen>
      <PageHeader title="知识" subtitle="豹纹守宫饲养与蜕皮护理" />

      {serverUrl === '' ? (
        <Card>
          <EmptyState
            icon="cloud-offline"
            title="先配置服务器"
            subtitle="到「设置」页填写服务器地址，才能加载知识库内容"
          />
        </Card>
      ) : topicsQuery.isLoading ? (
        <Card>
          <EmptyState icon="hourglass" title="加载中…" />
        </Card>
      ) : topicsQuery.isError ? (
        <Card>
          <EmptyState icon="cloud-offline" title="无法加载知识库" subtitle={topicsQuery.error.message} />
        </Card>
      ) : (
        <View style={styles.list}>
          {(topicsQuery.data?.items ?? []).map((topic, index) => (
            <Pressable
              key={topic.slug}
              onPress={() => router.push(`/topic/${topic.slug}`)}
              style={({ pressed }) => [styles.topicCard, pressed && styles.topicPressed]}
            >
              <View style={styles.indexBadge}>
                <Text style={styles.indexText}>{index + 1}</Text>
              </View>
              <View style={styles.topicBody}>
                <Text style={styles.topicTitle}>{topic.title}</Text>
                <Text style={styles.topicSummary} numberOfLines={2}>
                  {topic.summary}
                </Text>
              </View>
              <Text style={styles.chevron}>›</Text>
            </Pressable>
          ))}
        </View>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  list: { gap: 12 },
  topicCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.card,
    borderWidth: 3,
    borderColor: colors.border,
    borderRadius: radius.lg,
    padding: 16,
    gap: 12,
  },
  topicPressed: { opacity: 0.85 },
  indexBadge: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: colors.background,
    borderWidth: 2,
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  indexText: { fontSize: 15, fontWeight: '800', color: colors.primary },
  topicBody: { flex: 1, gap: 4 },
  topicTitle: { fontSize: 16, fontWeight: '700', color: colors.foreground },
  topicSummary: { fontSize: 13, lineHeight: 19, color: colors.mutedForeground },
  chevron: { fontSize: 26, color: colors.primary, fontWeight: '300' },
});
