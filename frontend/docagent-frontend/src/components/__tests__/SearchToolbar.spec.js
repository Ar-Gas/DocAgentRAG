import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import SearchToolbar from '@/components/SearchToolbar.vue'


const ElInput = {
  props: ['modelValue'],
  template: '<input :value="modelValue" />'
}

const ElButton = {
  props: ['loading', 'disabled'],
  emits: ['click'],
  template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>'
}

const ElOption = {
  props: ['label', 'value'],
  template: '<div class="el-option-stub" :data-label="label" :data-value="value"><slot /></div>'
}

const ElOptionGroup = {
  props: ['label'],
  template: '<div class="el-option-group-stub" :data-label="label"><slot /></div>'
}

const ElSelect = {
  props: ['modelValue', 'multiple', 'clearable', 'placeholder'],
  emits: ['update:modelValue'],
  template: `
    <div class="el-select-stub" :data-model-value="modelValue" :data-placeholder="placeholder">
      <slot />
    </div>
  `
}

const ElDatePicker = {
  props: ['modelValue'],
  template: '<div class="el-date-picker-stub" :data-model-value="JSON.stringify(modelValue || [])"></div>'
}

const ElSlider = {
  props: ['modelValue'],
  template: '<div class="el-slider-stub" :data-model-value="modelValue"></div>'
}

const ElSwitch = {
  props: ['modelValue'],
  template: '<div class="el-switch-stub" :data-model-value="String(modelValue)"></div>'
}

const ElIcon = { template: '<span class="el-icon-stub"><slot /></span>' }

const STUBS = {
  ElInput,
  ElButton,
  ElOption,
  ElOptionGroup,
  ElSelect,
  ElDatePicker,
  ElSlider,
  ElSwitch,
  ElIcon,
  Document: { template: '<span class="document-icon-stub" />' }
}

function mountToolbar(overrides = {}) {
  return mount(SearchToolbar, {
    props: {
      modelValue: {
        query: '',
        mode: 'hybrid',
        filename: '',
        file_types: [],
        classification: '',
        date_range: [],
        alpha: 0.5,
        use_rerank: true,
        use_query_expansion: false,
        use_llm_rerank: false
      },
      stats: {
        total_documents: 12,
        vector_indexed_documents: 8,
        file_types: { pdf: 4, docx: 3 }
      },
      categories: [
        {
          id: 'hr.offer_approval',
          label: 'Offer审批',
          path: ['人力资源', '招聘管理', 'Offer审批'],
          domain: '人力资源'
        },
        {
          id: 'finance.invoice',
          label: '发票审批',
          path: ['财务', '报销管理', '发票审批'],
          domain: '财务'
        },
        {
          id: 'hr.recruitment',
          label: '招聘总览',
          path: ['人力资源', '招聘管理', '招聘总览'],
          domain: '人力资源'
        }
      ],
      loading: false,
      canSummarize: false,
      canGenerateReport: false,
      rebuildingTopics: false,
      ...overrides
    },
    global: {
      stubs: STUBS
    }
  })
}

describe('SearchToolbar', () => {
  it('renders classification options grouped by domain with an all option first', () => {
    const wrapper = mountToolbar()

    const classificationSelect = wrapper.findAll('.el-select-stub')[2]
    const optionValues = classificationSelect.findAll('.el-option-stub').map((node) => ({
      label: node.attributes('data-label'),
      value: node.attributes('data-value')
    }))
    const groupLabels = classificationSelect.findAll('.el-option-group-stub').map((node) => node.attributes('data-label'))

    expect(optionValues[0]).toEqual({ label: '全部分类', value: '' })
    expect(groupLabels).toEqual(['人力资源', '财务'])
    expect(optionValues).toContainEqual({ label: 'Offer审批', value: 'hr.offer_approval' })
    expect(optionValues).toContainEqual({ label: '招聘总览', value: 'hr.recruitment' })
    expect(optionValues).toContainEqual({ label: '发票审批', value: 'finance.invoice' })
  })

  it('emits classification_id instead of raw label when a category is selected', async () => {
    const wrapper = mountToolbar()

    const selects = wrapper.findAllComponents(ElSelect)
    await selects[2].vm.$emit('update:modelValue', 'hr.offer_approval')

    expect(wrapper.emitted('update:modelValue')).toBeTruthy()
    expect(wrapper.emitted('update:modelValue').at(-1)[0]).toEqual(
      expect.objectContaining({
        classification: 'hr.offer_approval'
      })
    )
  })
})
