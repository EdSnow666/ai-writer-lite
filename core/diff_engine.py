# 职责: 三粒度 Diff 计算（段落/句子/词级）
# 依赖外部: difflib, jieba (可选)
# 暴露: calc_paragraph_diff(), calc_sentence_diff(), calc_word_diff_by_paragraph()

import difflib
import re

def calc_paragraph_diff(original, final):
    """整段对比"""
    paras_orig = original.split('\n\n')
    paras_final = final.split('\n\n')

    matcher = difflib.SequenceMatcher(None, paras_orig, paras_final)
    result = {'added': [], 'deleted': [], 'modified': []}

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'insert':
            result['added'].extend(paras_final[j1:j2])
        elif tag == 'delete':
            result['deleted'].extend(paras_orig[i1:i2])
        elif tag == 'replace':
            result['modified'].append({
                'from': paras_orig[i1:i2],
                'to': paras_final[j1:j2]
            })

    return result

def calc_sentence_diff(original, final):
    """句子级对比"""
    sents_orig = re.split(r'[。！？\.\!\?]', original)
    sents_final = re.split(r'[。！？\.\!\?]', final)

    matcher = difflib.SequenceMatcher(None, sents_orig, sents_final)
    result = {'added': [], 'deleted': [], 'modified': []}

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'insert':
            result['added'].extend(sents_final[j1:j2])
        elif tag == 'delete':
            result['deleted'].extend(sents_orig[i1:i2])
        elif tag == 'replace':
            result['modified'].append({
                'from': sents_orig[i1:i2],
                'to': sents_final[j1:j2]
            })

    return result

def calc_word_diff_by_paragraph(original, final):
    """按段落迭代词级对比，避免跨段错配"""
    try:
        import jieba
        has_jieba = True
    except ImportError:
        has_jieba = False

    paras_orig = original.split('\n\n')
    paras_final = final.split('\n\n')
    para_matcher = difflib.SequenceMatcher(None, paras_orig, paras_final)
    results = []

    for tag, i1, i2, j1, j2 in para_matcher.get_opcodes():
        if tag == 'equal':
            continue

        for i in range(i1, i2):
            for j in range(j1, j2):
                if has_jieba:
                    words_orig = list(jieba.cut(paras_orig[i]))
                    words_final = list(jieba.cut(paras_final[j]))
                else:
                    words_orig = paras_orig[i].split()
                    words_final = paras_final[j].split()

                word_matcher = difflib.SequenceMatcher(None, words_orig, words_final)
                para_diff = {'para_index_orig': i, 'para_index_final': j, 'added': [], 'deleted': [], 'modified': []}

                for wtag, wi1, wi2, wj1, wj2 in word_matcher.get_opcodes():
                    if wtag == 'insert':
                        para_diff['added'].append(''.join(words_final[wj1:wj2]))
                    elif wtag == 'delete':
                        para_diff['deleted'].append(''.join(words_orig[wi1:wi2]))
                    elif wtag == 'replace':
                        para_diff['modified'].append({'from': ''.join(words_orig[wi1:wi2]), 'to': ''.join(words_final[wj1:wj2])})

                results.append(para_diff)

    return results
