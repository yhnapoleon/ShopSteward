<script setup lang="ts">
import { t as tr } from '~/i18n'

// No plan waits for the owner: say what the mission is waiting for instead.
defineProps<{ working: boolean }>()
const { stock } = useShop()
const { status } = useTaskPresentation()
const { mission, ended } = useSpace()
</script>
<template>
  <article class="task-outcome glass space-outcome">
    <span class="task-outcome-icon"
      ><AppIcon
        :name="
          !mission
            ? 'loader-circle'
            : ended
              ? 'check-check'
              : working
                ? 'clock'
                : stock?.in_transit
                  ? 'truck'
                  : 'orbit'
        "
    /></span>
    <div>
      <h2>
        {{
          tr(
            !mission
              ? '正在读取这项委托'
              : ended
                ? mission.status === 'COMPLETED'
                  ? '这项委托已完成'
                  : '这项委托已取消'
                : working
                  ? '正在核实采购提交'
                  : stock?.in_transit
                    ? '等待到货'
                    : '暂时没有新的决定',
          )
        }}
      </h2>
      <p>{{ tr(mission ? status.detail : '方案、采购单与到货记录读取后显示在这里。') }}</p>
    </div>
  </article>
</template>
