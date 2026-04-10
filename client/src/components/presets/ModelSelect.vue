<template>
  <div class="relative">
    <div v-if="models.length > 0">
      <select
        :value="modelValue"
        @change="$emit('update:modelValue', $event.target.value)"
        class="w-full px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
               focus:outline-none focus:border-accent transition-colors appearance-none cursor-pointer"
      >
        <option value="">{{ placeholder }}</option>
        <option v-for="m in models" :key="m.id" :value="m.id">{{ m.name }}</option>
      </select>
    </div>
    <input
      v-else
      :value="modelValue"
      @input="$emit('update:modelValue', $event.target.value)"
      :placeholder="placeholder"
      class="w-full px-3 py-2 bg-bg-primary border border-border rounded-lg text-text-primary text-sm
             placeholder:text-text-muted focus:outline-none focus:border-accent transition-colors"
    />
  </div>
</template>

<script setup>
defineProps({
  modelValue: String,
  models: { type: Array, default: () => [] },
  placeholder: { type: String, default: 'Select model...' },
});
defineEmits(['update:modelValue']);
</script>
