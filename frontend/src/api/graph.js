import service, { requestWithRetry } from './index'

/**
 * Генерация онтологии (загрузка документов и требований к симуляции)
 * @param {Object} data - содержит files, simulation_requirement, project_name и т.д.
 * @returns {Promise}
 */
export function generateOntology(formData) {
  return requestWithRetry(() =>
    service({
      url: '/api/graph/ontology/generate',
      method: 'post',
      data: formData,
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
  )
}

/**
 * Построение графа
 * @param {Object} data - содержит project_id, graph_name и т.д.
 * @returns {Promise}
 */
export function buildGraph(data) {
  return requestWithRetry(() =>
    service({
      url: '/api/graph/build',
      method: 'post',
      data
    })
  )
}

/**
 * Запрос статуса задачи
 * @param {String} taskId - ID задачи
 * @returns {Promise}
 */
export function getTaskStatus(taskId) {
  return service({
    url: `/api/graph/task/${taskId}`,
    method: 'get'
  })
}

/**
 * Получение данных графа
 * @param {String} graphId - ID графа
 * @returns {Promise}
 */
export function getGraphData(graphId) {
  return service({
    url: `/api/graph/data/${graphId}`,
    method: 'get'
  })
}

/**
 * Получение информации о проекте
 * @param {String} projectId - ID проекта
 * @returns {Promise}
 */
export function getProject(projectId) {
  return service({
    url: `/api/graph/project/${projectId}`,
    method: 'get'
  })
}
