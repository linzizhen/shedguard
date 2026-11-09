/**
 * 蜕皮日志 Tab（骨架占位）。
 * 实现计划：宠物切换 + 记录时间线 + 下次蜕皮预测卡片（GET shed-prediction）。
 */
import { Card, EmptyState, PageHeader, Screen } from '@/components/ui';

export default function LogScreen() {
  return (
    <Screen>
      <PageHeader title="蜕皮日志" subtitle="记录每次蜕皮，预测下一次" />
      <Card style={{ paddingVertical: 24 }}>
        <EmptyState
          icon="calendar"
          title="日志功能开发中"
          subtitle="支持记录蜕皮起止日期、查看历史时间线与下次蜕皮预测"
        />
      </Card>
    </Screen>
  );
}
