import request from './index'

export const searchKnowledge = (data) => request.post('/knowledge/search', data)
