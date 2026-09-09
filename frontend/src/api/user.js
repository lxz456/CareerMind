import request from './index'

export const getProfile = () => request.get('/users/me')
export const updateProfile = (data) => request.put('/users/me', data)
