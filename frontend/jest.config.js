const nextJest = require('next/jest.js')

const createJestConfig = nextJest({ dir: './' })

const config = {
  testEnvironment: 'jsdom',
}

module.exports = createJestConfig(config)
