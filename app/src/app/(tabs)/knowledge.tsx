/**
 * 知识 Tab（骨架占位）。
 * 实现计划：GET /api/v1/knowledge/topics 六话题卡片列表 + 详情页。
 */
import { Card, EmptyState, PageHeader, Screen } from '@/components/ui';

export default function KnowledgeScreen() {
  return (
    <Screen>
      <PageHeader title="知识" subtitle="豹纹守宫饲养与蜕皮护理" />
      <Card style={{ paddingVertical: 24 }}>
        <EmptyState
          icon="book"
          title="知识库开发中"
          subtitle="六个话题：速览 / 环境 / 喂食 / 蜕皮基础 / 卡皮处理 / 加湿"
        />
      </Card>
    </Screen>
  );
}
