<script setup lang="ts">
import { t as tr } from '~/i18n'
import type { QuoteRow } from '~/surfaces/types'

// Organized quote lines as given; a missing value says so instead of becoming zero.
defineProps<{ rows: QuoteRow[] }>()
</script>
<template>
  <div class="surface-comparison">
    <div class="work-result-table surface-table" tabindex="0" :aria-label="tr('报价结果表格')">
      <table>
        <thead>
          <tr>
            <th scope="col">{{ tr('商品') }}</th>
            <th scope="col">{{ tr('单件价') }}</th>
            <th scope="col">{{ tr('包装件数') }}</th>
            <th scope="col">{{ tr('最低订购量') }}</th>
            <th scope="col">{{ tr('来源') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, index) in rows" :key="index">
            <td>{{ row.product }}</td>
            <td>{{ row.unitPrice ?? tr('未提供') }}</td>
            <td>{{ row.pack ?? tr('未提供') }}</td>
            <td>{{ row.minimumOrder ?? tr('未提供') }}</td>
            <td>{{ row.source ?? tr('未提供') }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
