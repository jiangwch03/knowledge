import useDictStore from '@/store/modules/dict'
import { getDicts } from '@/api/system/dict/data'

/**
 * 获取字典数据
 */
export function useDict(...args) {
  const res = ref({});
  return (() => {
    args.forEach((dictType, index) => {
      res.value[dictType] = [];
      const dicts = useDictStore().getDict(dictType);
      // 空数组视为未命中，避免首次缓存 miss 后一直显示「无数据」
      if (dicts && dicts.length) {
        res.value[dictType] = dicts;
      } else {
        getDicts(dictType).then(resp => {
          res.value[dictType] = (resp.data || []).map(p => ({ label: p.dictLabel, value: p.dictValue, elTagType: p.listClass, elTagClass: p.cssClass }))
          if (res.value[dictType].length) {
            useDictStore().setDict(dictType, res.value[dictType]);
          }
        })
      }
    })
    return toRefs(res.value);
  })()
}