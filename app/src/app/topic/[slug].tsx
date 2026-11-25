/**
 * 知识详情页（根级路由，带 Stack 返回按钮）。
 * 后端：GET /api/v1/knowledge/topics/{slug}。
 * 纸感极简（P34）：正文靠留白与 1px 纸线分节，小标题用 Eyebrow。
 */
import { useLocalSearchParams } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';

import { Divider, EmptyState, Eyebrow, Screen } from '@/components/ui';
import { useKnowledgeTopic } from '@/hooks/useKnowledge';
import { colors, space, type } from '@/lib/theme';

export default function TopicDetailScreen() {
  const { slug } = useLocalSearchParams<{ slug: string }>();
  const topicQuery = useKnowledgeTopic(slug);

  if (topicQuery.isLoading) {
    return (
      <Screen>
        <Text style={styles.summary}>加载中…</Text>
      </Screen>
    );
  }

  if (topicQuery.isError || !topicQuery.data) {
    return (
      <Screen>
        <EmptyState
          title="无法加载这篇内容"
          subtitle={topicQuery.error?.message ?? '内容不存在'}
        />
      </Screen>
    );
  }

  const topic = topicQuery.data;

  return (
    <Screen>
      <Text style={styles.title}>{topic.title}</Text>
      <Text style={styles.summary}>{topic.summary}</Text>

      {topic.sections.map((section) => (
        <View key={section.heading} style={styles.section}>
          <Divider />
          <Eyebrow>{section.heading}</Eyebrow>
          {section.bullets.map((bullet, index) => (
            <View key={index} style={styles.bulletRow}>
              <View style={styles.bulletDot} />
              <Text style={styles.bulletText}>{bullet}</Text>
            </View>
          ))}
        </View>
      ))}
    </Screen>
  );
}

const styles = StyleSheet.create({
  title: {
    ...type.display,
    fontSize: 26,
    lineHeight: 34,
    color: colors.foreground,
  },
  summary: {
    ...type.body,
    color: colors.mutedForeground,
  },
  section: {
    gap: space.sm,
    marginTop: space.xs,
  },
  bulletRow: {
    flexDirection: 'row',
    gap: space.md,
    paddingRight: space.xs,
    alignItems: 'flex-start',
  },
  bulletDot: {
    width: 4,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.accent,
    marginTop: 9,
  },
  bulletText: {
    flex: 1,
    ...type.body,
    color: colors.body,
  },
});
